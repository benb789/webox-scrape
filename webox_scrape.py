import argparse
import csv
import datetime
import json
import os
import re
import sys

try:
    import requests
except ImportError:
    print("The requests library is required. Install it with: python -m pip install requests")
    sys.exit(1)


def parse_cookie_string(cookie_header: str) -> dict:
    cookies = {}
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = value.strip()
    return cookies


API_URL = "https://www.webox.com/api/product/menu/v1/page"

COOKIE_HEADER = '_ga=GA1.1.389911738.1764552323; messagesUtk=1678c375df004ecd993a1f9d9693f468; hubspotutk=b8fd6985bb62199ad69ae96e9fa60f89; __stripe_mid=bb716410-91d0-4a77-9ee2-bcf6733d2224dbd2d3; X-Auth-Token=eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjM1MzI4MSwiYWNjb3VudCI6ImJlbi5ib3JuQGFzdGVyYWxhYnMuY29tIiwidHlwZSI6IlVzZXIiLCJyb2xlcyI6WyJCMkJDdXN0b21lciJdLCJpZGVudGlmaWVyIjoiMTU1NDA0NzgxMDIzMDAiLCJleHAiOjE3ODQzMTUxOTEsImlhdCI6MTc3NjUzOTE5MSwianRpIjoiZWRiMzg5YTQtNjI2NS00YTE2LWIyZTktZjc1OGU5NDQ2NDQ1In0=.kp4vkUao3BYwhcVhUbFlwODIeuBu3y8DK82h0sBZXwHkWXOrakwNI8B6S2cMrtiHadwmCyX-N16g_9TuDdIeTxkQ0WUvymImrmuuiOMT09V9x71LOlBRsZNPR-wEhuZRejyd4GVlXJ-Fcq6DPgXDr2Jh_WQiiJe0pptqaJo7fvI=; __stripe_sid=c2a19f4b-8492-4a44-9443-ba3f11cd8c51451cc9; hs-messages-hide-welcome-message=true; __hstc=139470316.b8fd6985bb62199ad69ae96e9fa60f89.1764552325058.1776547190241.1776549984456.7; __hssrc=1; _ga_DY6TSYXVV7=GS2.1.s1776541670$o3$g1$t1776550474$j60$l0$h0; g_state={"i_l":0,"i_ll":1776550474372,"i_b":"uA31K2TbigbgCRZd9M06yqpSQod96tZcqEPXjwDLYDM","i_e":{"enable_itp_optimization":0},"i_et":1776539147195}; __hssc=139470316.4.1776549984456; _ga_9V0QHVJMZB=GS2.1.s1776547188$o4$g1$t1776550475$j58$l0$h0'

DEFAULT_FILTER = {
    "parentCategoryId": None,
    "cuisine": None,
    "primaryType": None,
    "priceFrom": None,
    "priceTo": None,
    "orderBy": None,
    "packagingTypes": None,
    "pageIndex": 0,
    "pageSize": 3000,
    "parentCategoryId": None,
    "priceFrom": None,
    "priceTo": None,
    "primaryType": None,
    "ratingFrom": None,
    "ratingTo": None,
    "queryText": " ",
}

CSV_FIELDS = [
    "productId",
    "price",
    "regularPrice",
    "stockStatus",
    "partnerId",
    "brandId",
    "itemName",
    "productRatingCount",
    "productAverageRating",
    "category",
    "authentic",
    "salesCnt",
    "partnerName",
    "partnerAverageRating",
    "partnerRatingCount",
    "partnerRatingCommentCount",
]


def build_payload(address_id: int, date_shipping: str, time_shipping: str, catering: bool, page_index: int, page_size: int) -> dict:
    return {
        "addressId": address_id,
        "dateShipping": date_shipping,
        "timeShipping": time_shipping,
        "catering": catering,
        "filterOption": {
            **DEFAULT_FILTER,
            "pageIndex": page_index,
            "pageSize": page_size,
        },
    }


def fetch_specials(payload: dict, cookie_header: str | None = None) -> dict:
    params = {"client": "web"}
    headers = {"Content-Type": "application/json"}
    cookies = parse_cookie_string(cookie_header) if cookie_header else None
    response = requests.post(
        API_URL,
        params=params,
        json=payload,
        headers=headers,
        cookies=cookies,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def fetch_all_specials(address_id: int, date_shipping: str, time_shipping: str, catering: bool, page_index: int, page_size: int, cookie_header: str | None = None) -> tuple[list[dict], int | None, dict[int, dict]]:
    all_items: list[dict] = []
    total_count = None
    brand_map: dict[int, dict] = {}
    while True:
        payload = build_payload(
            address_id=address_id,
            date_shipping=date_shipping,
            time_shipping=time_shipping,
            catering=catering,
            page_index=page_index,
            page_size=page_size,
        )
        print(f"Fetching page {page_index} (pageSize={page_size})...")
        data = fetch_specials(payload, cookie_header=cookie_header)
        if data.get("code") != 1:
            raise RuntimeError(f"Unexpected API response code: {data.get('code')}")
        page_data = data.get("data", {})
        if total_count is None:
            total_count = page_data.get("totalCount")
        page_items = page_data.get("specials", [])
        all_items.extend(page_items)
        page_brands = page_data.get("brands", [])
        for brand in page_brands:
            brand_id = brand.get("id")
            if brand_id is not None:
                brand_map[brand_id] = brand
        if not page_items:
            break
        if total_count is not None and len(all_items) >= total_count:
            break
        if len(page_items) < page_size:
            break
        page_index += 1
    return all_items, total_count, brand_map


def normalize_item(item: dict, brand_map: dict[int, dict]) -> dict:
    ext_product = item.get("extProduct", {}) or {}
    brand = brand_map.get(ext_product.get("brandId"), {}) if ext_product.get("brandId") is not None else {}
    normalized = {
        "productId": item.get("productId", ""),
        "price": item.get("price", ""),
        "regularPrice": item.get("regularPrice", ""),
        "stockStatus": item.get("stockStatus", ""),
        "partnerId": item.get("partnerId", ""),
        "brandId": ext_product.get("brandId", ""),
        "itemName": (ext_product.get("extName") or {}).get("enUs", ""),
        "productRatingCount": ext_product.get("ratingCount", ""),
        "productAverageRating": ext_product.get("averageRating", ""),
        "category": ext_product.get("category", ""),
        "authentic": ext_product.get("authentic", ""),
        "salesCnt": ext_product.get("salesCnt", ""),
        "partnerName": (brand.get("extName") or {}).get("enUs", ""),
        "partnerAverageRating": brand.get("averageRating", ""),
        "partnerRatingCount": brand.get("ratingCount", ""),
        "partnerRatingCommentCount": brand.get("ratingCommentCount", ""),
    }
    return normalized


def write_csv(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def upload_to_drive(csv_path: str, folder_name: str, service_account_json_str: str) -> str:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(service_account_json_str),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    service = build("drive", "v3", credentials=credentials)

    results = service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
    ).execute()
    folders = results.get("files", [])
    if not folders:
        raise RuntimeError(f"Drive folder '{folder_name}' not found")
    folder_id = folders[0]["id"]

    file_basename = os.path.basename(csv_path)
    existing = service.files().list(
        q=f"name='{file_basename}' and '{folder_id}' in parents and trashed=false",
        fields="files(id, name)",
    ).execute().get("files", [])
    if existing:
        service.files().delete(fileId=existing[0]["id"]).execute()
        print(f"Deleted existing file: {file_basename}")

    file_metadata = {"name": file_basename, "parents": [folder_id]}
    media = MediaFileUpload(csv_path, mimetype="text/csv")
    uploaded = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    file_id = uploaded.get("id")
    print(f"Uploaded {file_basename} to Drive folder '{folder_name}' (id={file_id})")
    return file_id


def cleanup_old_files(folder_name: str, service_account_json_str: str, keep_days: int = 5) -> None:
    from googleapiclient.discovery import build
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_info(
        json.loads(service_account_json_str),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    service = build("drive", "v3", credentials=credentials)

    results = service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
    ).execute()
    folders = results.get("files", [])
    if not folders:
        print(f"Drive folder '{folder_name}' not found — skipping cleanup.")
        return
    folder_id = folders[0]["id"]

    csv_files = service.files().list(
        q=f"'{folder_id}' in parents and name contains '.csv' and trashed=false",
        fields="files(id, name)",
    ).execute().get("files", [])

    today = datetime.date.today()
    workdays: set[datetime.date] = set()
    d = today
    while len(workdays) < keep_days:
        if d.weekday() < 5:
            workdays.add(d)
        d -= datetime.timedelta(days=1)

    pattern = re.compile(r"webox_menu_(\d{4}-\d{2}-\d{2})_lunch\.csv")
    for f in csv_files:
        m = pattern.match(f["name"])
        if m:
            file_date = datetime.date.fromisoformat(m.group(1))
            if file_date not in workdays:
                service.files().delete(fileId=f["id"]).execute()
                print(f"Deleted old file: {f['name']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Webox daily food items and export them to CSV.")
    parser.add_argument("--date", default=None, help="Shipping date in YYYY-MM-DD format")
    parser.add_argument("--time", default="Lunch", help="Time shipping label, e.g. Lunch, Dinner")
    parser.add_argument("--address-id", type=int, default=None, help="Address ID for the request")
    parser.add_argument("--cookie", default=None, help="Raw cookie header string for authenticated requests")
    parser.add_argument("--output", default=None, help="Output CSV path")
    parser.add_argument("--page-index", type=int, default=0, help="Page index for pagination")
    parser.add_argument("--page-size", type=int, default=50, help="Page size for pagination")
    parser.add_argument("--catering", action="store_true", help="Include catering items")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Priority order: CLI arg → env var → interactive prompt / default
    date = args.date or os.environ.get("WEBOX_DATE") or input("Enter date: ")
    address_id = args.address_id or int(os.environ.get("WEBOX_ADDRESS_ID", 239098))
    cookie = args.cookie or os.environ.get("WEBOX_COOKIE") or COOKIE_HEADER

    payload = build_payload(
        address_id=address_id,
        date_shipping=date,
        time_shipping=args.time,
        catering=args.catering,
        page_index=args.page_index,
        page_size=args.page_size,
    )

    if os.environ.get("GITHUB_ACTIONS"):
        default_output = f"webox_menu_{date}_{args.time.lower()}.csv"
    else:
        default_output = os.path.join(
            os.path.expanduser("~"), "OneDrive", "Desktop",
            f"webox_menu_{date}_{args.time.lower()}.csv"
        )
    output_path = args.output or default_output
    print(f"Requesting {API_URL}?client=web for date={date} time={args.time} pageSize={args.page_size}")
    try:
        specials, total_count, brand_map = fetch_all_specials(
            address_id=address_id,
            date_shipping=date,
            time_shipping=args.time,
            catering=args.catering,
            page_index=args.page_index,
            page_size=args.page_size,
            cookie_header=cookie,
        )
    except Exception as exc:
        print(f"Error fetching specials: {exc}")
        return 1

    if not specials:
        print("No specials were returned by the API.")
    else:
        if total_count is not None:
            print(f"Received {len(specials)} of {total_count} total items from the API.")
        else:
            print(f"Received {len(specials)} items from the API.")

    rows = [normalize_item(item, brand_map) for item in specials]
    write_csv(output_path, rows)
    print(f"Saved {len(rows)} rows to {output_path}")

    service_account_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if service_account_json:
        upload_to_drive(output_path, "WeBox Daily Menus", service_account_json)
        cleanup_old_files("WeBox Daily Menus", service_account_json, keep_days=5)
    else:
        print("GOOGLE_SERVICE_ACCOUNT_JSON not set — skipping Drive upload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
