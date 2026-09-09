import OpenAI from 'openai';

const client = new OpenAI({
  baseURL: 'https://api.deepseek.com',
  apiKey: process.env.DEEPSEEK_API_KEY,
});
async function main() {
  const response = await client.chat.completions.create({
    model: 'deepseek-v4-pro',
    messages: [{ role: 'user', content: 'Hello!' }],
    thinking: { type: 'enabled' },
    reasoning_effort: 'high',
    stream: false,
  });
  console.log(response.choices[0].message.content);
}
main();
