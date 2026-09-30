import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from urllib.parse import urljoin


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://devanture.net/stats.php?cat=6"
DOMAIN = "https://www.devanture.net"

OUTPUT_FILE = "morocco_mines_data.xlsx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
}


session = requests.Session()
session.headers.update(HEADERS)


# ============================================================
# GET PAGE
# ============================================================

def get_page(url):

    print(f"GET: {url}")

    response = session.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    return response


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(text):

    if not text:
        return None

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


# ============================================================
# STEP 1
# GET REGIONS FROM STATS PAGE
# ============================================================

print()
print("=" * 70)
print("STEP 1 — FINDING REGIONS")
print("=" * 70)

response = get_page(BASE_URL)

soup = BeautifulSoup(
    response.text,
    "html.parser"
)

regions = []

table = soup.find("table")

if not table:

    print("ERROR: statistics table not found.")

    exit()


for row in table.find_all("tr")[1:]:

    cells = row.find_all("td")

    if len(cells) < 5:
        continue

    region_name = clean_text(
        cells[1].get_text(" ", strip=True)
    )

    mine_count = clean_text(
        cells[2].get_text(" ", strip=True)
    )

    link = cells[4].find(
        "a",
        href=True
    )

    if not link:
        continue

    href = link["href"]

    region_url = urljoin(
        "https://devanture.net/",
        href
    )

    regions.append(
        {
            "Region": region_name,
            "Expected_Mines": mine_count,
            "Region_URL": region_url
        }
    )


print()
print(
    f"Regions found: {len(regions)}"
)

for region in regions:

    print(
        f"{region['Region']} "
        f"-> {region['Expected_Mines']} mines "
        f"-> {region['Region_URL']}"
    )


# ============================================================
# STEP 2
# FOLLOW REGION REDIRECT
# ============================================================

print()
print("=" * 70)
print("STEP 2 — OPENING REGION PAGES")
print("=" * 70)


region_pages = []

for region in regions:

    try:

        response = get_page(
            region["Region_URL"]
        )

        # The website gives:
        #
        # <meta http-equiv="refresh"
        # content="1;url=https://www.devanture.net/regions.php?r_id=2">

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        meta = soup.find(
            "meta",
            attrs={
                "http-equiv": re.compile(
                    "^refresh$",
                    re.I
                )
            }
        )

        target_url = None

        if meta:

            content = meta.get(
                "content",
                ""
            )

            match = re.search(
                r"url\s*=\s*(.+)",
                content,
                re.I
            )

            if match:

                target_url = match.group(1).strip()

                target_url = target_url.strip(
                    "\"'"
                )


        # If no meta redirect was found,
        # requests may have followed a normal redirect.
        if not target_url:

            target_url = response.url


        print(
            f"{region['Region']} -> {target_url}"
        )

        region_pages.append(
            {
                "Region": region["Region"],
                "Expected_Mines": region["Expected_Mines"],
                "URL": target_url
            }
        )

    except Exception as e:

        print(
            f"ERROR: {region['Region']}: {e}"
        )


# ============================================================
# STEP 3
# FIND MINE LINKS ON regions.php
# ============================================================
print()
print("=" * 70)
print("STEP 3 — FINDING MINE PAGES")
print("=" * 70)
all_mines = []
for region in region_pages:
    print()
    print(f"[{region['Region']}]")
    try:
        response = get_page(region["URL"])
        soup = BeautifulSoup(response.text, "html.parser")
        print("HTML size:", len(response.content))
        mine_links = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            absolute_url = urljoin(DOMAIN + "/", href)

            # --- MODIFIED LOGIC ---
            # We are now specifically looking for URLs that contain
            # '/details.php?id=' which seems to be the pattern for mine pages.
            # We also check if the link text or surrounding elements suggest it's a mine.
            # You might need to further refine this based on inspecting the HTML
            # of a few 'region' pages to find the most reliable pattern.
            if "/details.php?id=" in absolute_url:
                # Further check to ensure it's a mine and not another facility type
                # This is a crucial step for filtering. We'll look for keywords
                # in the link's text or its parent elements.
                link_text = link.get_text(strip=True).lower()
                # Add keywords that indicate a mine. Adjust as needed.
                if "mine" in link_text or "gisement" in link_text or "carrière" in link_text:
                    mine_links.append(absolute_url)
                # --- END MODIFIED LOGIC ---

        # Remove duplicates
        mine_links = list(dict.fromkeys(mine_links))
        print("Mine links found:", len(mine_links))
        for mine_url in mine_links:
            all_mines.append({
                "Region": region["Region"],
                "Mine_URL": mine_url
            })
    except Exception as e:
        print(f"ERROR: {e}")

# Remove duplicate URLs again, just in case
unique = {}
for mine in all_mines:
    unique[mine["Mine_URL"]] = mine
all_mines = list(unique.values())
print()
print("=" * 70)
print("TOTAL UNIQUE MINE LINKS:", len(all_mines))
print("=" * 70)

# ... rest of the script (STEP 4, 5, 6) remains the same ...

# ============================================================
# IMPORTANT DEBUG
# ============================================================

if len(all_mines) == 0:

    print()
    print(
        "NO MINE LINKS FOUND."
    )

    print()
    print(
        "The region pages are accessible, "
        "but their mine URL structure is different "
        "from the patterns currently detected."
    )

    print()
    print(
        "Saving one region page for inspection..."
    )

    if region_pages:

        debug_response = get_page(
            region_pages[0]["URL"]
        )

        with open(
            "region_real_page.html",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                debug_response.text
            )

        print(
            "Saved: region_real_page.html"
        )

    exit()


# ============================================================
# STEP 4
# SCRAPE INDIVIDUAL MINE PAGES
# ============================================================

print()
print("=" * 70)
print("STEP 4 — SCRAPING INDIVIDUAL MINES")
print("=" * 70)


records = []


for index, mine in enumerate(
    all_mines,
    start=1
):

    print()
    print(
        f"[{index}/{len(all_mines)}]"
    )

    print(
        mine["Mine_URL"]
    )

    try:

        time.sleep(1)

        response = get_page(
            mine["Mine_URL"]
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )


        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        title = None

        h1 = soup.find("h1")

        if h1:

            title = clean_text(
                h1.get_text(
                    " ",
                    strip=True
                )
            )

        elif soup.title:

            title = clean_text(
                soup.title.get_text(
                    " ",
                    strip=True
                )
            )


        # ----------------------------------------------------
        # FULL PAGE TEXT
        # ----------------------------------------------------

        page_text = clean_text(
            soup.get_text(
                " ",
                strip=True
            )
        )


        # ----------------------------------------------------
        # STORE RAW DATA FOR NOW
        # ----------------------------------------------------

        records.append(
            {
                "Mine_Name": title,
                "Region": mine["Region"],
                "Detail_URL": mine["Mine_URL"],
                "Full_Page_Text": page_text
            }
        )


    except Exception as e:

        print(
            "ERROR:",
            e
        )


# ============================================================
# STEP 5
# DATAFRAME
# ============================================================

print()
print("=" * 70)
print("STEP 5 — BUILDING DATASET")
print("=" * 70)


if not records:

    print(
        "No mine records were scraped."
    )

    exit()


df = pd.DataFrame(
    records
)


df.insert(
    0,
    "Record_ID",
    range(
        1,
        len(df) + 1
    )
)


# ============================================================
# STEP 6
# EXPORT
# ============================================================

print()
print("=" * 70)
print("STEP 6 — EXPORTING EXCEL")
print("=" * 70)


with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl"
) as writer:

    df.to_excel(
        writer,
        sheet_name="Mines",
        index=False
    )

    summary = (
        df.groupby("Region")
        .size()
        .reset_index(
            name="Scraped_Mines"
        )
        .sort_values(
            "Scraped_Mines",
            ascending=False
        )
    )

    summary.to_excel(
        writer,
        sheet_name="Regional_Summary",
        index=False
    )


print()
print("=" * 70)
print("DONE")
print("=" * 70)

print(
    f"Total mines scraped: {len(df)}"
)

print(
    f"Output: {OUTPUT_FILE}"
)