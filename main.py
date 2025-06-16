

from scripts.ai.generate_audios.generate_audio import generate_audio_for_items
from scripts.ai.generate_images.generate_images import generate_images
from scripts.ai.generate_list.generate_list import generate_list
from scripts.non_ai.generate_video_short.generate_video_short import generate_video_short
from scripts.non_ai.create_titled_images_short.create_titled_images_short import create_titled_images_for_items_short


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
    generate_images(items_json)

    # Then generate titled images for the items
    print("\nGenerating titled images for items...")
    create_titled_images_for_items_short(items_json)

    # Then generate video for the items
    print("\nGenerating video for items...")
    generate_video_short()

if __name__ == "__main__":
    main()
    