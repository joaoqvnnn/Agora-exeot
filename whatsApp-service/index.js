/* ============================================
   📱 WHATSAPP SERVICE — Larizinha Store
   ============================================
   Serviço Node.js que conecta ao WhatsApp via Baileys.

   🎯 FOCO DESTA VERSÃO:
     - QR Code em tamanho NORMAL (320px)
     - Página limpa e fácil de printar
     - Endpoint /qr.png pra baixar só a imagem
     - Sem QR gigante

   Endpoints:
     GET  /                    → status geral
     GET  /status              → status detalhado
     GET  /qr                  → página com QR
     GET  /qr.png              → imagem do QR
     POST /send                → enviar mensagem
     POST /send-media          → enviar mídia
     POST /check-number        → verificar número
     POST /logout              → desconectar
     POST /restart             → reiniciar
     POST /new-qr              → gerar novo QR
   ============================================ */

import express from 'express';
import cors from 'cors';
import qrcode from 'qrcode';
import axios from 'axios';
import pino from 'pino';
import dotenv from 'dotenv';
import makeWASocket, {
    useMultiFileAuthState,
    DisconnectReason,
    fetchLatestBaileysVersion,
    Browsers,
    makeCacheableSignalKeyStore,
    isJidBroadcast,
    isJidGroup,
} from '@whiskeysockets/baileys';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

// ============================================
// ⚙️ CONFIGURAÇÃO
// ============================================
dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PORT = process.env.PORT || 3000;
const WEBHOOK_URL = process.env.WEBHOOK_URL || '';
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || '';
const AUTH_DIR = process.env.AUTH_DIR || path.join(__dirname, 'auth_info');
const SERVICE_API_KEY = process.env.SERVICE_API_KEY || '';

const logger = pino({
    level: process.env.LOG_LEVEL || 'warn',
});

// ============================================
// 🌐 ESTADO GLOBAL
// ============================================
const State = {
    sock: null,
    qr: null,
    qrGeneratedAt: null,
    connected: false,
    connecting: false,
    lastDisconnect: null,
    phoneNumber: null,
    pushName: null,
    startedAt: new Date().toISOString(),
    messagesSent: 0,
    messagesReceived: 0,
};

// ============================================
// 📁 PASTA DE AUTH
// ============================================
function ensureAuthDir() {
    if (!fs.existsSync(AUTH_DIR)) {
        fs.mkdirSync(AUTH_DIR, { recursive: true });
        console.log(`📁 Pasta de auth criada: ${AUTH_DIR}`);
    }
}

function clearAuthDir() {
    try {
        if (fs.existsSync(AUTH_DIR)) {
            fs.rmSync(AUTH_DIR, { recursive: true, force: true });
            console.log('🧹 Pasta de auth limpa');
        }
    } catch (err) {
        console.error('⚠️ Falha ao limpar auth:', err.message);
    }
}

// ============================================
// 🔌 CONECTA AO WHATSAPP
// ============================================
async function connectToWhatsApp() {
    if (State.connecting || State.connected) {
        console.log('⚠️ Já conectando ou conectado');
        return;
    }

    State.connecting = true;
    ensureAuthDir();

    try {
        const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
        const { version } = await fetchLatestBaileysVersion();

        console.log(`🤖 Baileys versão: ${version.join('.')}`);

        const sock = makeWASocket({
            version,
            logger,
            printQRInTerminal: false,   // ⚠️ Desligado — usamos endpoint /qr
            browser: Browsers.ubuntu('Chrome'),
            auth: {
                creds: state.creds,
                keys: makeCacheableSignalKeyStore(state.keys, logger),
            },
            generateHighQualityLinkPreview: false,
            syncFullHistory: false,
            markOnlineOnConnect: false,
            getMessage: async () => undefined,
        });

        State.sock = sock;

        sock.ev.on('creds.update', saveCreds);

        // ─── Conexão ───
        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                State.qr = qr;
                State.qrGeneratedAt = new Date().toISOString();
                State.connected = false;

                console.log('');
                console.log('═══════════════════════════════════════');
                console.log('📸 NOVO QR CODE GERADO');
                console.log('═══════════════════════════════════════');
                console.log('');
                console.log('👉 ACESSE ESTE LINK NO NAVEGADOR:');
                console.log(`   http://localhost:${PORT}/qr`);
                console.log('');
                console.log('   (Ou no Render:)');
                console.log(`   https://SEU-SERVICO.onrender.com/qr`);
                console.log('');
                console.log('📱 Escaneie o QR que aparecer na página');
                console.log('═══════════════════════════════════════');
                console.log('');
            }

            if (connection === 'open') {
                State.connected = true;
                State.connecting = false;
                State.qr = null;
                State.qrGeneratedAt = null;
                State.lastDisconnect = null;

                const user = sock.user;
                State.phoneNumber = user?.id?.split(':')[0] || user?.id || null;
                State.pushName = user?.name || null;

                console.log('');
                console.log('═══════════════════════════════════════');
                console.log(`✅ CONECTADO: ${State.pushName}`);
                console.log(`📞 Número: ${State.phoneNumber}`);
                console.log('═══════════════════════════════════════');
                console.log('');

                await notifyWebhook({
                    event: 'connected',
                    phone: State.phoneNumber,
                    pushName: State.pushName,
                });
            }

            if (connection === 'close') {
                State.connected = false;
                State.connecting = false;

                const reason = lastDisconnect?.error?.output?.statusCode;
                State.lastDisconnect = {
                    reason,
                    at: new Date().toISOString(),
                };

                console.log(`❌ Desconectado (reason: ${reason})`);

                if (reason === DisconnectReason.loggedOut) {
                    console.log('🚪 Logout — limpando credenciais');
                    clearAuthDir();
                    return;
                }

                if (reason === DisconnectReason.connectionClosed ||
                    reason === DisconnectReason.connectionLost ||
                    reason === DisconnectReason.restartRequired ||
                    reason === DisconnectReason.timedOut) {
                    console.log('🔄 Reconectando em 5s...');
                    setTimeout(() => connectToWhatsApp(), 5000);
                }
            }
        });

        // ─── Mensagens ───
        sock.ev.on('messages.upsert', async (m) => {
            try {
                if (m.type !== 'notify') return;

                for (const msg of m.messages) {
                    if (msg.key.fromMe) continue;
                    if (isJidBroadcast(msg.key.remoteJid)) continue;
                    if (isJidGroup(msg.key.remoteJid)) continue;

                    State.messagesReceived++;

                    const from = msg.key.remoteJid;
                    const messageText = extractText(msg);

                    if (!messageText) continue;

                    const payload = {
                        event: 'message',
                        from,
                        messageId: msg.key.id,
                        timestamp: msg.messageTimestamp,
                        text: messageText,
                        pushName: msg.pushName || null,
                        messageType: getMessageType(msg),
                    };

                    console.log(`📩 ${from}: ${messageText.slice(0, 50)}`);

                    await notifyWebhook(payload);
                }
            } catch (err) {
                console.error('❌ Erro ao processar mensagem:', err.message);
            }
        });

    } catch (err) {
        console.error('❌ Erro na conexão:', err.message);
        State.connecting = false;
        setTimeout(() => connectToWhatsApp(), 10000);
    }
}

// ============================================
// 📝 EXTRAI TEXTO
// ============================================
function extractText(msg) {
    const m = msg.message;
    if (!m) return null;

    if (m.conversation) return m.conversation;
    if (m.extendedTextMessage?.text) return m.extendedTextMessage.text;
    if (m.imageMessage?.caption) return m.imageMessage.caption;
    if (m.videoMessage?.caption) return m.videoMessage.caption;
    if (m.documentMessage?.caption) return m.documentMessage.caption;

    if (m.buttonsResponseMessage?.selectedButtonId)
        return m.buttonsResponseMessage.selectedButtonId;
    if (m.listResponseMessage?.singleSelectReply?.selectedRowId)
        return m.listResponseMessage.singleSelectReply.selectedRowId;

    return null;
}

function getMessageType(msg) {
    const m = msg.message;
    if (!m) return 'unknown';

    if (m.conversation || m.extendedTextMessage) return 'text';
    if (m.imageMessage) return 'image';
    if (m.videoMessage) return 'video';
    if (m.audioMessage) return 'audio';
    if (m.documentMessage) return 'document';
    if (m.stickerMessage) return 'sticker';

    return 'other';
}

// ============================================
// 📤 WEBHOOK
// ============================================
async function notifyWebhook(payload) {
    if (!WEBHOOK_URL) return;

    try {
        const headers = { 'Content-Type': 'application/json' };
        if (WEBHOOK_SECRET) headers['X-Webhook-Secret'] = WEBHOOK_SECRET;

        await axios.post(WEBHOOK_URL, payload, {
            headers,
            timeout: 10000,
        });
    } catch (err) {
        console.error('⚠️ Webhook falhou:', err.message);
    }
}

// ============================================
// 📞 NORMALIZA NÚMERO
// ============================================
function normalizeNumber(phone) {
    let digits = String(phone).replace(/\D/g, '');
    if (digits.startsWith('0')) digits = digits.slice(1);
    if (!digits.startsWith('55') && digits.length <= 11) {
        digits = '55' + digits;
    }
    return digits;
}

function toJid(phone) {
    return `${normalizeNumber(phone)}@s.whatsapp.net`;
}

// ============================================
// 🌐 EXPRESS
// ============================================
const app = express();

app.use(cors());
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

function requireApiKey(req, res, next) {
    if (!SERVICE_API_KEY) return next();
    const key = req.headers['x-api-key'] || req.query.api_key;
    if (key !== SERVICE_API_KEY) {
        return res.status(401).json({ ok: false, error: 'API key inválida' });
    }
    next();
}

// ============================================
// 🏥 STATUS
// ============================================
app.get('/', (req, res) => {
    res.json({
        ok: true,
        service: 'Larizinha WhatsApp Service',
        version: '1.0.0',
        status: State.connected ? 'connected' : (State.qr ? 'awaiting_qr' : 'disconnected'),
        uptime: process.uptime(),
    });
});

app.get('/status', (req, res) => {
    res.json({
        ok: true,
        connected: State.connected,
        connecting: State.connecting,
        hasQr: !!State.qr,
        phoneNumber: State.phoneNumber,
        pushName: State.pushName,
        lastDisconnect: State.lastDisconnect,
        stats: {
            messagesSent: State.messagesSent,
            messagesReceived: State.messagesReceived,
        },
    });
});

// ============================================
// 📸 QR — IMAGEM PNG PURA (pra printar direto)
// ============================================
app.get('/qr.png', async (req, res) => {
    if (!State.qr) {
        return res.status(404).json({ ok: false, error: 'Sem QR no momento' });
    }

    try {
        const buffer = await qrcode.toBuffer(State.qr, {
            width: 320,
            margin: 2,
            color: {
                dark: '#000000',
                light: '#ffffff',
            },
            errorCorrectionLevel: 'M',
        });

        res.set('Content-Type', 'image/png');
        res.set('Cache-Control', 'no-cache, no-store, must-revalidate');
        res.send(buffer);
    } catch (err) {
        console.error('❌ Erro ao gerar QR:', err.message);
        res.status(500).json({ ok: false, error: 'Erro ao gerar QR' });
    }
});

// ============================================
// 📸 QR — PÁGINA LIMPA COM QR TAMANHO NORMAL
// ============================================
app.get('/qr', async (req, res) => {
    // ─── Já conectado ───
    if (State.connected) {
        return res.send(renderConnectedPage());
    }

    // ─── Sem QR ainda ───
    if (!State.qr) {
        return res.send(renderWaitingPage());
    }

    // ─── Tem QR — mostra em tamanho NORMAL ───
    try {
        const qrDataUrl = await qrcode.toDataURL(State.qr, {
            width: 320,          // 👈 TAMANHO NORMAL
            margin: 2,
            color: {
                dark: '#000000',
                light: '#ffffff',
            },
            errorCorrectionLevel: 'M',
        });

        res.send(renderQrPage(qrDataUrl));
    } catch (err) {
        console.error('❌ Erro ao gerar QR:', err.message);
        res.status(500).send('Erro ao gerar QR Code');
    }
});

// ============================================
// 🎨 TEMPLATES HTML
// ============================================
function renderConnectedPage() {
    return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhatsApp Conectado</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f7;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #333;
        }
        .card {
            background: #fff;
            border-radius: 24px;
            padding: 48px 32px;
            max-width: 420px;
            width: 100%;
            text-align: center;
            box-shadow: 0 10px 40px rgba(0,0,0,0.08);
        }
        .icon {
            width: 100px;
            height: 100px;
            border-radius: 50%;
            background: linear-gradient(135deg, #25D366, #128C7E);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 56px;
            margin: 0 auto 24px;
            color: #fff;
        }
        h1 { font-size: 24px; font-weight: 700; margin-bottom: 12px; color: #111; }
        p { color: #666; font-size: 15px; line-height: 1.6; margin-bottom: 24px; }
        .info {
            background: #f9f9fb;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 20px;
            text-align: left;
        }
        .info-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            font-size: 14px;
        }
        .info-row + .info-row { border-top: 1px solid #eee; }
        .info-label { color: #888; }
        .info-value { color: #111; font-weight: 600; }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✓</div>
        <h1>WhatsApp Conectado</h1>
        <p>Seu WhatsApp está ativo e pronto para receber mensagens.</p>

        <div class="info">
            <div class="info-row">
                <span class="info-label">Número</span>
                <span class="info-value">${State.phoneNumber || '—'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Nome</span>
                <span class="info-value">${State.pushName || '—'}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Mensagens enviadas</span>
                <span class="info-value">${State.messagesSent}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Mensagens recebidas</span>
                <span class="info-value">${State.messagesReceived}</span>
            </div>
        </div>

        <p style="font-size: 13px; color: #999; margin-bottom: 0;">
            Esta página atualiza automaticamente.
        </p>
    </div>
    <script>setTimeout(() => location.reload(), 10000);</script>
</body>
</html>`;
}

function renderWaitingPage() {
    return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="3">
    <title>Aguardando QR</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f7;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            text-align: center;
            color: #333;
        }
        .card {
            background: #fff;
            border-radius: 24px;
            padding: 48px 32px;
            max-width: 420px;
            width: 100%;
            box-shadow: 0 10px 40px rgba(0,0,0,0.08);
        }
        .spinner {
            width: 64px;
            height: 64px;
            border: 5px solid #e5e5e7;
            border-top-color: #25D366;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 24px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        h1 { font-size: 22px; font-weight: 700; margin-bottom: 12px; color: #111; }
        p { color: #666; font-size: 15px; line-height: 1.6; }
        .small { font-size: 13px; color: #999; margin-top: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="spinner"></div>
        <h1>Aguardando QR Code...</h1>
        <p>O QR Code aparecerá aqui em alguns segundos.</p>
        <p class="small">Esta página atualiza sozinha.</p>
    </div>
</body>
</html>`;
}

function renderQrPage(qrDataUrl) {
    return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta http-equiv="refresh" content="45">
    <title>Escaneie o QR — WhatsApp</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f7;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            color: #333;
        }
        .card {
            background: #fff;
            border-radius: 24px;
            padding: 32px 24px;
            max-width: 420px;
            width: 100%;
            text-align: center;
            box-shadow: 0 10px 40px rgba(0,0,0,0.08);
        }
        .logo {
            width: 64px;
            height: 64px;
            border-radius: 20px;
            background: linear-gradient(135deg, #25D366, #128C7E);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 32px;
            margin: 0 auto 20px;
            color: #fff;
        }
        h1 {
            font-size: 22px;
            font-weight: 700;
            margin-bottom: 8px;
            color: #111;
        }
        p {
            color: #666;
            font-size: 14px;
            line-height: 1.6;
            margin-bottom: 20px;
        }
        .qr-box {
            background: #fff;
            border: 2px solid #e5e5e7;
            border-radius: 16px;
            padding: 16px;
            display: inline-block;
            margin-bottom: 20px;
        }
        .qr-box img {
            display: block;
            width: 320px;        /* 👈 TAMANHO NORMAL */
            height: 320px;
            image-rendering: pixelated;
        }
        .steps {
            background: #f9f9fb;
            border-radius: 12px;
            padding: 16px;
            text-align: left;
            font-size: 14px;
            color: #555;
            line-height: 1.8;
            margin-bottom: 16px;
        }
        .steps strong { color: #111; }
        .steps ol { padding-left: 20px; }
        .steps li { margin-bottom: 4px; }
        .refresh-note {
            font-size: 12px;
            color: #999;
        }
        .download-link {
            display: inline-block;
            margin-top: 12px;
            font-size: 13px;
            color: #25D366;
            text-decoration: none;
            font-weight: 600;
        }
        .download-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="card">
        <div class="logo">📱</div>
        <h1>Conectar WhatsApp</h1>
        <p>Escaneie o QR abaixo com seu WhatsApp</p>

        <div class="qr-box">
            <img src="${qrDataUrl}" alt="QR Code WhatsApp">
        </div>

        <div class="steps">
            <strong>Como conectar:</strong>
            <ol>
                <li>Abra o WhatsApp no seu celular</li>
                <li>Toque em <strong>Configurações</strong></li>
                <li>Toque em <strong>Aparelhos conectados</strong></li>
                <li>Toque em <strong>Conectar um aparelho</strong></li>
                <li>Aponte a câmera para o QR acima</li>
            </ol>
        </div>

        <a href="/qr.png" class="download-link" target="_blank">
            📥 Baixar QR em imagem
        </a>

        <p class="refresh-note">
            🔄 Atualiza automaticamente a cada 45 segundos
        </p>
    </div>
</body>
</html>`;
}

// ============================================
// 📤 ENVIAR MENSAGEM
// ============================================
app.post('/send', requireApiKey, async (req, res) => {
    try {
        const { phone, message, text } = req.body;
        const body = message || text;

        if (!phone || !body) {
            return res.status(400).json({
                ok: false,
                error: 'Faltam campos: phone e message',
            });
        }

        if (!State.connected || !State.sock) {
            return res.status(503).json({
                ok: false,
                error: 'WhatsApp não conectado',
            });
        }

        const jid = toJid(phone);

        await State.sock.sendMessage(jid, { text: body });

        State.messagesSent++;

        console.log(`📤 Enviado para ${phone}: ${body.slice(0, 50)}`);

        res.json({
            ok: true,
            sent: true,
            to: jid,
        });
    } catch (err) {
        console.error('❌ Erro ao enviar:', err.message);
        res.status(500).json({
            ok: false,
            error: err.message || 'Erro ao enviar mensagem',
        });
    }
});

// ============================================
// 📎 ENVIAR MÍDIA
// ============================================
app.post('/send-media', requireApiKey, async (req, res) => {
    try {
        const { phone, mediaUrl, mediaType, caption } = req.body;

        if (!phone || !mediaUrl) {
            return res.status(400).json({
                ok: false,
                error: 'Faltam campos: phone e mediaUrl',
            });
        }

        if (!State.connected || !State.sock) {
            return res.status(503).json({
                ok: false,
                error: 'WhatsApp não conectado',
            });
        }

        const jid = toJid(phone);
        const type = (mediaType || 'image').toLowerCase();

        let messageContent = {};

        if (type === 'image') {
            messageContent = {
                image: { url: mediaUrl },
                caption: caption || undefined,
            };
        } else if (type === 'video') {
            messageContent = {
                video: { url: mediaUrl },
                caption: caption || undefined,
            };
        } else if (type === 'document') {
            messageContent = {
                document: { url: mediaUrl },
                mimetype: 'application/pdf',
                fileName: 'documento.pdf',
                caption: caption || undefined,
            };
        } else {
            return res.status(400).json({
                ok: false,
                error: `Tipo não suportado: ${type}`,
            });
        }

        await State.sock.sendMessage(jid, messageContent);

        State.messagesSent++;

        res.json({ ok: true, sent: true, to: jid });
    } catch (err) {
        console.error('❌ Erro ao enviar mídia:', err.message);
        res.status(500).json({
            ok: false,
            error: err.message || 'Erro ao enviar mídia',
        });
    }
});

// ============================================
// 🔍 VERIFICAR NÚMERO
// ============================================
app.post('/check-number', requireApiKey, async (req, res) => {
    try {
        const { phone } = req.body;

        if (!phone) {
            return res.status(400).json({
                ok: false,
                error: 'Falta campo: phone',
            });
        }

        if (!State.connected || !State.sock) {
            return res.status(503).json({
                ok: false,
                error: 'WhatsApp não conectado',
            });
        }

        const jid = toJid(phone);
        const result = await State.sock.onWhatsApp(jid);

        if (result && result.length > 0) {
            res.json({ ok: true, exists: true, jid: result[0].jid });
        } else {
            res.json({ ok: true, exists: false });
        }
    } catch (err) {
        console.error('❌ Erro ao verificar número:', err.message);
        res.status(500).json({ ok: false, error: err.message });
    }
});

// ============================================
// 🚪 LOGOUT
// ============================================
app.post('/logout', requireApiKey, async (req, res) => {
    try {
        if (State.sock) {
            await State.sock.logout();
        }

        State.connected = false;
        State.qr = null;
        State.phoneNumber = null;
        State.pushName = null;

        clearAuthDir();

        res.json({ ok: true, message: 'Desconectado' });

        setTimeout(() => connectToWhatsApp(), 3000);
    } catch (err) {
        console.error('❌ Erro no logout:', err.message);
        res.status(500).json({ ok: false, error: err.message });
    }
});

// ============================================
// 🔄 REINICIAR CONEXÃO
// ============================================
app.post('/restart', requireApiKey, async (req, res) => {
    try {
        if (State.sock) {
            try { State.sock.end(undefined); } catch (e) {}
        }

        State.connected = false;
        State.connecting = false;
        State.qr = null;
        State.sock = null;

        setTimeout(() => connectToWhatsApp(), 1000);

        res.json({ ok: true, message: 'Reiniciando...' });
    } catch (err) {
        res.status(500).json({ ok: false, error: err.message });
    }
});

// ============================================
// 📸 FORÇA NOVO QR
// ============================================
app.post('/new-qr', requireApiKey, async (req, res) => {
    try {
        if (State.sock) {
            try { State.sock.end(undefined); } catch (e) {}
        }

        clearAuthDir();

        State.connected = false;
        State.connecting = false;
        State.qr = null;
        State.sock = null;

        setTimeout(() => connectToWhatsApp(), 1500);

        res.json({ ok: true, message: 'Gerando novo QR...' });
    } catch (err) {
        res.status(500).json({ ok: false, error: err.message });
    }
});

// ============================================
// 🚀 START
// ============================================
app.listen(PORT, () => {
    console.log('');
    console.log('═══════════════════════════════════════');
    console.log('🚀 WhatsApp Service — Larizinha Store');
    console.log('═══════════════════════════════════════');
    console.log(`📡 Porta: ${PORT}`);
    console.log(`📡 WEBHOOK_URL: ${WEBHOOK_URL || '(não configurado)'}`);
    console.log(`📁 AUTH_DIR: ${AUTH_DIR}`);
    console.log('');
    console.log('📱 Conectando ao WhatsApp...');
    console.log('   (Aguarde o QR aparecer)');
    console.log('═══════════════════════════════════════');
    console.log('');

    connectToWhatsApp();
});

// ============================================
// 🛑 SHUTDOWN
// ============================================
process.on('SIGTERM', async () => {
    console.log('🛑 SIGTERM recebido');
    if (State.sock) {
        try { State.sock.end(undefined); } catch (e) {}
    }
    process.exit(0);
});

process.on('SIGINT', async () => {
    console.log('🛑 SIGINT recebido');
    if (State.sock) {
        try { State.sock.end(undefined); } catch (e) {}
    }
    process.exit(0);
});

process.on('uncaughtException', (err) => {
    console.error('❌ Uncaught:', err);
});

process.on('unhandledRejection', (err) => {
    console.error('❌ Rejection:', err);
});
