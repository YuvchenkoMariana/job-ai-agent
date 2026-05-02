from PIL import Image

for size in [16, 48, 128]:
    img = Image.new('RGB', (size, size), color='#4CAF50')
    img.save(f'icon{size}.png')
    print(f'Created icon{size}.png')
