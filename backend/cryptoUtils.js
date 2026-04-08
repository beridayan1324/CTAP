const crypto = require('crypto');
require('dotenv').config();

// Must match client - loaded from environment variables
const FIXED_AES_KEY_HEX = process.env.AES_KEY_HEX;
const HANDSHAKE_SECRET = process.env.HANDSHAKE_SECRET;

if (!FIXED_AES_KEY_HEX || FIXED_AES_KEY_HEX.length !== 64) {
    throw new Error('[FATAL] AES_KEY_HEX environment variable is not set or invalid (must be 64 hex chars)');
}
if (!HANDSHAKE_SECRET) {
    throw new Error('[FATAL] HANDSHAKE_SECRET environment variable is not set');
}

const AES_KEY = Buffer.from(FIXED_AES_KEY_HEX, 'hex');

const decryptPayload = (payload) => {
    try {
        const nonce = Buffer.from(payload.nonce, 'base64');
        const ciphertextWithTag = Buffer.from(payload.ciphertext, 'base64');

        // GCM tag is the last 16 bytes
        const tagLength = 16;
        const ciphertext = ciphertextWithTag.subarray(0, ciphertextWithTag.length - tagLength);
        const tag = ciphertextWithTag.subarray(ciphertextWithTag.length - tagLength);

        const decipher = crypto.createDecipheriv('aes-256-gcm', AES_KEY, nonce);
        decipher.setAuthTag(tag);

        let plaintext = decipher.update(ciphertext, undefined, 'utf8');
        plaintext += decipher.final('utf8');

        return plaintext;
    } catch (e) {
        return `[DECRYPTION FAILED] ${e.message}`;
    }
};

const encryptPayload = (plaintext) => {
    const nonce = crypto.randomBytes(12);
    const cipher = crypto.createCipheriv('aes-256-gcm', AES_KEY, nonce);
    
    const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
    const tag = cipher.getAuthTag();
    
    const ciphertextWithTag = Buffer.concat([ciphertext, tag]);

    return {
        nonce: nonce.toString('base64'),
        ciphertext: ciphertextWithTag.toString('base64')
    };
};

const verifyHandshakeHash = (challenge, responseHash) => {
    const expectedHash = crypto.createHash('sha256')
        .update(challenge + HANDSHAKE_SECRET)
        .digest('hex');
    // Use timingSafeEqual to prevent timing attacks
    const expectedBuf = Buffer.from(expectedHash, 'hex');
    const responseBuf = Buffer.from(responseHash, 'hex');
    if (expectedBuf.length !== responseBuf.length) return false;
    return crypto.timingSafeEqual(expectedBuf, responseBuf);
};

const generateChallenge = () => {
    return crypto.randomBytes(32).toString('hex');
};

const generateHash = (content) => {
    return crypto.createHash('sha256').update(content).digest('hex');
};

module.exports = {
    decryptPayload,
    encryptPayload,
    verifyHandshakeHash,
    generateChallenge,
    generateHash,
    HANDSHAKE_SECRET
};
