"""CLI utility to manage dataset quarantine list."""

import argparse

from sentinel.preflight import DatasetQuarantine


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage quarantined dataset checksums.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all quarantined checksums.")
    group.add_argument(
        "--add", type=str, metavar="CHECKSUM", help="Manually quarantine a checksum."
    )
    group.add_argument(
        "--release", type=str, metavar="CHECKSUM", help="Manually release/remove a checksum."
    )

    args = parser.parse_args()

    if args.list:
        checksums = DatasetQuarantine.list_all()
        if not checksums:
            print("No datasets are currently quarantined.")
        else:
            print("Quarantined Datasets:")
            for c in checksums:
                print(f"  - {c}")
    elif args.add:
        DatasetQuarantine.add(args.add)
        print(f"Successfully quarantined checksum: {args.add}")
    elif args.release:
        removed = DatasetQuarantine.remove(args.release)
        if removed:
            print(f"Successfully released checksum: {args.release}")
        else:
            print(f"Checksum was not quarantined: {args.release}")


if __name__ == "__main__":
    main()
