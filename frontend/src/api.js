export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.status = status;
    }
}

/** Vékony fetch-wrapper: Bearer token, JSON, időkorlát, értelmes hibaüzenet. */
export function createApi(token, { base = '', fetchImpl = (...args) => fetch(...args), timeoutMs = 15000 } = {}) {
    async function request(method, path, body, { timeout = timeoutMs } = {}) {
        let response;
        try {
            response = await fetchImpl(base + path, {
                method,
                headers: {
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
                },
                body: body !== undefined ? JSON.stringify(body) : undefined,
                signal: AbortSignal.timeout(timeout),
            });
        } catch {
            throw new ApiError('A szerver nem érhető el (offline?)', 0);
        }
        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try {
                const data = await response.json();
                if (typeof data.detail === 'string') detail = data.detail;
                else if (Array.isArray(data.detail)) detail = data.detail.map((d) => d.msg).join('; ');
            } catch { /* nem JSON válasz */ }
            throw new ApiError(detail, response.status);
        }
        return response.json();
    }

    return {
        get: (path, options) => request('GET', path, undefined, options),
        post: (path, body, options) => request('POST', path, body, options),
        put: (path, body) => request('PUT', path, body),
    };
}
