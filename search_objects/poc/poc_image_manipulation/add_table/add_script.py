import base64
from openai import OpenAI

client = OpenAI()

prompt = """
Image 1: empty room photograph. This is the destination scene.
Image 2: product photograph. This is the object to insert.

Task:
Place the product from Image 2 into the empty center of the room in Image 1.

Keep from Image 1:
- camera angle, vanishing points, and perspective
- floor plane, walls, windows, and existing furniture
- lighting, color temperature, and shadows
- framing and composition

From Image 2:
- keep the same product design: shape, materials, legs, color, and proportions
- re-render it from Image 1's camera so it sits correctly on the floor
- scale the product to a realistic size for this room

Integration:
- the product must rest correctly for that product 
- add photorealistic contact shadows matching the room light
- do not paste the product as a flat cutout
- do not redesign the room or invent a different product

Photorealistic photograph. Change only the insertion of the product.
"""

# Image 1 = room, Image 2 = product. The model never sees filenames.
with open("room.jpg", "rb") as room_file, open("table.jpg", "rb") as product_file:
    response = client.images.edit(
        model="gpt-image-2.5-sunburst",
        image=[room_file, product_file],
        prompt=prompt,
        n=1,
        size="auto",
        quality="high",
        output_format="png",
    )

image_base64 = response.data[0].b64_json

if image_base64:
    image_bytes = base64.b64decode(image_base64)
    with open("final_room_design.png", "wb") as file:
        file.write(image_bytes)
    print("Success! Your images have been merged into 'final_room_design.png'.")
else:
    print(f"Image URL: {response.data[0].url}")
