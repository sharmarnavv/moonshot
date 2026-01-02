import ollama
import base64
import io

# A single red pixel PNG
RED_DOT_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
image_bytes = base64.b64decode(RED_DOT_B64)

print(f"🧐 Sending {len(image_bytes)} bytes to Ollama (moondream)...")

try:
    response = ollama.chat(
        model='moondream',
        messages=[{
            'role': 'user',
            'content': 'Describe this image color',
            'images': [image_bytes]
        }]
    )
    print("✅ Response:")
    print(response['message']['content'])
except Exception as e:
    print(f"❌ Error: {e}")
