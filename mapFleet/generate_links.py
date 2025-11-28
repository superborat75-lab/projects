# generate_links.py

from services.gmaps_links_multi import generate_gmaps_links_for_all_vehicles


if __name__ == "__main__":
    links = generate_gmaps_links_for_all_vehicles(
        output_dir="data/output",
        max_addresses_per_link=8,
        write_txt=True,
        open_in_browser=True,   # да отваря ли нещо в браузъра изобщо
        open_delay_seconds=2.0, # debounce интервал между линковете (секунди)
        open_all_links=True,   # ако True -> ще отвори ВСИЧКИ линкове за всяка кола
    )

    print("\n📍 Generated Google Maps links (per vehicle):")
    for vehicle, urls in links.items():
        print(f"\n🚚 {vehicle}:")
        for i, url in enumerate(urls, start=1):
            print(f"  google_map_link_{i}: '{url}'")
