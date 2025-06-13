from generate_image_v2 import generate_images_for_items_v2
from generate_list import generate_list
from generate_audio import generate_audio_for_items
from generate_image import generate_images_for_items
from generate_titled_image import generate_titled_images_for_items
from generate_titled_image_v2 import generate_titled_images_for_items_v2
from generate_video import generate_video
from generate_video_v2 import generate_video_v2


def main():
    # Get the topic from user input
    topic = input("Enter a topic for your video: ")
    
    # First generate the list of items
    print("\nGenerating list of items...")
    items_json = generate_list(topic)
    
    # Then generate audio for the items
    print("\nGenerating audio for items...")
    generate_audio_for_items(items_json)

    # Then generate images for the items
    print("\nGenerating images for items...")
    generate_images_for_items(items_json)

    # Then generate titled images for the items
    print("\nGenerating titled images for items...")
    generate_titled_images_for_items(items_json)

    # Then generate video for the items
    print("\nGenerating video for items...")
    generate_video()

def main_v2():
    # Get the topic from user input
    topic = input("Enter a topic for your video: ")
    
    # First generate the list of items
    print("\nGenerating list of items...")
    items_json = generate_list(topic)
    
    # Then generate audio for the items
    print("\nGenerating audio for items...")
    generate_audio_for_items(items_json)

    # Then generate images for the items
    print("\nGenerating images for items...")
    generate_images_for_items_v2(items_json)

    # Then generate titled images for the items
    print("\nGenerating titled images for items...")
    generate_titled_images_for_items_v2(items_json)

    # Then generate video for the items
    print("\nGenerating video for items...")
    generate_video_v2()

if __name__ == "__main__":
    main()
    #main_v2()