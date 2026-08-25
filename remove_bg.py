import os
from rembg import remove
from PIL import Image

def main():
    input_path = os.path.join('assets', 'logo', 'j.png')
    output_path = os.path.join('assets', 'logo', 'j.png')
    
    if not os.path.exists(input_path):
        print(f"File not found: {input_path}")
        return

    print("Removing background...")
    input_image = Image.open(input_path)
    output_image = remove(input_image)
    output_image.save(output_path)
    print(f"Saved background-removed image to {output_path}")

if __name__ == "__main__":
    main()
