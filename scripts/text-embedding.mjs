import { request } from 'https';

async function embedText(text)
{

    const data = JSON.stringify({
    model: "jina-embeddings-v5-text-small",
    task: "retrieval.query",
    normalized: true,
    input: [text]
    });

    const options = {
    hostname: 'api.jina.ai',
    path: '/v1/embeddings',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.HUGGINGFACE_API_KEY}`,
        'Content-Length': data.length
    }
    };

    const req = request(options, (res) => {
    let responseBody = '';

    res.on('data', (chunk) => {
        responseBody += chunk;
    });

    res.on('end', () => {
        console.log(JSON.parse(responseBody).data);
    });
    });

    req.on('error', (e) => {
    console.error(`Problem with request: ${e.message}`);
    });

    // Write data to request body
    req.write(data);
    req.end();
}