from openai import OpenAI

client = OpenAI(
    base_url="https://api.respan.ai/api/",
    api_key="YOUR_RESPAN_API_KEY",
)

response = client.chat.completions.create(
    model="gpt-5.4",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)