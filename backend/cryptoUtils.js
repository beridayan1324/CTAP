const crypto = require('crypto');

// Must match client
const FIXED_AES_KEY_HEX = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f";
const HANDSHAKE_SECRET = "CTAP-GLOVE-AUTH-2026";

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
    return expectedHash === responseHash;
};

const generateChallenge = () => {
    return crypto.randomBytes(16).toString('hex');
};

const generateHash = (content) => {
    return crypto.createHash('sha256').update(content).digest('hex');
};

module.exports = {
    decryptPayload,
    encryptPayload, // Used for the client mostly
    verifyHandshakeHash,
    generateChallenge,
    generateHash,
    HANDSHAKE_SECRET
};
