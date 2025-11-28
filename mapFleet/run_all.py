# run_all.py
import subprocess
import sys


def run(cmd: list[str]):
    print(f"\n➡️  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"❌ Command failed with code {result.returncode}: {' '.join(cmd)}")
        sys.exit(result.returncode)


def main():
    # ----------------------------------------------------
    # 1) ROUTE GENERATION
    # ----------------------------------------------------
    # Ако искаш нов ден & изчистване на output:
    #    python run_all.py --no-cache
    #
    # Ако искаш да използваш готовите CSV:
    #    python run_all.py
    # ----------------------------------------------------

    cached = True
    if len(sys.argv) > 1 and sys.argv[1] == "--no-cache":
        cached = False

    if cached:
        print("\n🟢 Using cached CSV if present (no new Google API calls).")
        run(["python", "main.py"])
    else:
        print("\n🔴 FORCING NEW ROUTES (Google API calls + cleaning output).")
        run(["python", "main.py", "--no-cache"])

    # ----------------------------------------------------
    # 2) LINK GENERATION
    # ----------------------------------------------------
    print("\n📍 Generating Google Maps links from CSV…")
    run(["python", "generate_links.py"])

    print("\n✅ ALL DONE.\n")


if __name__ == "__main__":
    main()
