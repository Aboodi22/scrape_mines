import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from urllib.parse import urljoin, urlparse, parse_qs


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://devanture.net/stats.php?cat=6"
DOMAIN = "https://devanture.net"

OUTPUT_FILE = "morocco_mines_data.xlsx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/154.0 Safari/537.36"
    )
}

REQUEST_DELAY = 1


# ============================================================
# SESSION
# ============================================================

session = requests.Session()
session.headers.update(HEADERS)


def get_soup(url):
    """Download a page and return BeautifulSoup."""
    
    print(f"GET: {url}")

    response = session.get(url, timeout=30)
    response.raise_for_status()

    return BeautifulSoup(response.text, "html.parser")


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(value):
    if not value:
        return None

    value = re.sub(r"\s+", " ", value)
    return value.strip()


# ============================================================
# EXTRACT FIELD FROM DETAIL PAGE
# ============================================================

def extract_field(soup, label):
    """
    Find text such as:

    Adresse:
    Téléphone:
    Email:
    Superficie Totale:
    Date d'ouverture:
    """

    text = soup.get_text(" ", strip=True)

    pattern = rf"{re.escape(label)}\s*:\s*(.*?)(?=\s+(?:📞|✉️|📐|📅|###)|$)"

    match = re.search(pattern, text, re.IGNORECASE)

    if match:
        return clean_text(match.group(1))

    return None


# ============================================================
# GET INDIVIDUAL MINE LINKS FROM REGION PAGE
# ============================================================

def extract_mine_links(region_url):

    soup = get_soup(region_url)

    mine_links = []

    for link in soup.find_all("a", href=True):

        href = link["href"]

        absolute_url = urljoin(DOMAIN, href)

        # The site has detail URLs such as:
        #
        # /details.php?id=597
        # /detail/xxxxx-645
        #
        if (
            "/details.php" in absolute_url
            or "/detail/" in absolute_url
        ):

            mine_links.append(absolute_url)

    # Remove duplicates while preserving order
    mine_links = list(dict.fromkeys(mine_links))

    return mine_links


# ============================================================
# EXTRACT MINE INFORMATION
# ============================================================

def scrape_mine(detail_url, region):

    try:

        time.sleep(REQUEST_DELAY)

        soup = get_soup(detail_url)

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        h1 = soup.find("h1")

        mine_name = clean_text(h1.get_text(" ", strip=True)) if h1 else None

        # ----------------------------------------------------
        # FULL TEXT
        # ----------------------------------------------------

        page_text = clean_text(
            soup.get_text(" ", strip=True)
        )

        # ----------------------------------------------------
        # TYPE
        # ----------------------------------------------------

        mine_type = None

        # Usually appears directly below the title
        if h1:

            next_text = []

            for element in h1.find_all_next():

                text = clean_text(element.get_text(" ", strip=True))

                if text:
                    next_text.append(text)

                if len(next_text) >= 5:
                    break

            for text in next_text:

                if (
                    "Mine d'" in text
                    or "Mine de " in text
                    or "Mine " in text
                ):
                    mine_type = text
                    break

        # ----------------------------------------------------
        # CONTACT / TECHNICAL FIELDS
        # ----------------------------------------------------

        address = extract_field(
            soup,
            "Adresse"
        )

        phone = extract_field(
            soup,
            "Téléphone"
        )

        email = extract_field(
            soup,
            "Email"
        )

        superficie = extract_field(
            soup,
            "Superficie Totale"
        )

        opening_date = extract_field(
            soup,
            "Date d'ouverture"
        )

        # ----------------------------------------------------
        # DESCRIPTION
        # ----------------------------------------------------

        description = None

        # Look for heading containing "Description"
        description_heading = soup.find(
            lambda tag:
            tag.name in ["h2", "h3", "h4", "strong"]
            and "description" in tag.get_text(
                " ",
                strip=True
            ).lower()
        )

        if description_heading:

            parts = []

            for element in description_heading.find_all_next():

                if element == description_heading:
                    continue

                text = clean_text(
                    element.get_text(" ", strip=True)
                )

                if text:

                    parts.append(text)

                if len(parts) >= 3:
                    break

            if parts:
                description = " ".join(parts)

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        # IMPORTANT:
        # Do not invent operating status.
        #
        # The website does not consistently expose
        # an explicit "active/closed" field.

        status = "Not specified"

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        return {
            "Mine_Name": mine_name,
            "Type": mine_type,
            "Region": region,
            "Address": address,
            "Phone": phone,
            "Email": email,
            "Superficie_Totale": superficie,
            "Date_Opening": opening_date,
            "Description": description,
            "Status": status,
            "Detail_URL": detail_url,
            "Source": DOMAIN
        }

    except Exception as e:

        print(
            f"ERROR scraping {detail_url}: {e}"
        )

        return None


# ============================================================
# STEP 1 — GET THE 12 REGIONS
# ============================================================

print("\n========================================")
print("STEP 1 — GETTING REGIONS")
print("========================================\n")

stats_soup = get_soup(BASE_URL)

region_links = []

for link in stats_soup.find_all("a", href=True):

    href = link["href"]

    absolute_url = urljoin(DOMAIN, href)

    # The statistics page links to:
    #
    # region.php?cat=6&id=...

    if "region.php" in absolute_url:

        parsed = urlparse(absolute_url)

        params = parse_qs(parsed.query)

        if params.get("cat") == ["6"]:

            region_name = clean_text(
                link.get_text(" ", strip=True)
            )

            region_links.append(
                {
                    "Region": region_name,
                    "URL": absolute_url
                }
            )


# Remove duplicate regions
unique_regions = {}

for region in region_links:

    unique_regions[region["URL"]] = region

region_links = list(unique_regions.values())

print(
    f"\nFound {len(region_links)} mine-region pages."
)


# ============================================================
# STEP 2 — GET ALL MINE LINKS
# ============================================================

print("\n========================================")
print("STEP 2 — FINDING INDIVIDUAL MINES")
print("========================================\n")

all_mines = []

for index, region in enumerate(region_links, start=1):

    print(
        f"\n[{index}/{len(region_links)}] "
        f"{region['Region']}"
    )

    try:

        mine_links = extract_mine_links(
            region["URL"]
        )

        print(
            f"  Found {len(mine_links)} mine pages"
        )

        for mine_url in mine_links:

            all_mines.append(
                {
                    "Region": region["Region"],
                    "URL": mine_url
                }
            )

    except Exception as e:

        print(
            f"  ERROR: {e}"
        )


# Remove duplicates
unique_mines = {}

for mine in all_mines:

    unique_mines[mine["URL"]] = mine

all_mines = list(unique_mines.values())


print(
    f"\nTOTAL UNIQUE MINE PAGES FOUND: "
    f"{len(all_mines)}"
)


# ============================================================
# STEP 3 — SCRAPE EACH MINE
# ============================================================

print("\n========================================")
print("STEP 3 — SCRAPING MINE DETAILS")
print("========================================\n")

records = []

for index, mine in enumerate(all_mines, start=1):

    print(
        f"\n[{index}/{len(all_mines)}]"
    )

    record = scrape_mine(
        mine["URL"],
        mine["Region"]
    )

    if record:

        records.append(record)


# ============================================================
# STEP 4 — CREATE DATAFRAME
# ============================================================

df = pd.DataFrame(records)


# ============================================================
# CLEAN DATA
# ============================================================

print("\n========================================")
print("STEP 4 — CLEANING")
print("========================================\n")


for column in df.columns:

    if df[column].dtype == "object":

        df[column] = (
            df[column]
            .astype(str)
            .str.replace(
                r"\s+",
                " ",
                regex=True
            )
            .str.strip()
        )


# Remove completely duplicated mines
df = df.drop_duplicates(
    subset=["Detail_URL"]
)


# Add source ID if available
df.insert(
    0,
    "Record_ID",
    range(1, len(df) + 1)
)


# ============================================================
# STEP 5 — EXPORT EXCEL
# ============================================================

print("\n========================================")
print("STEP 5 — EXPORT")
print("========================================\n")

with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl"
) as writer:

    # ------------------------------------
    # ALL MINES
    # ------------------------------------

    df.to_excel(
        writer,
        sheet_name="Mines",
        index=False
    )

    # ------------------------------------
    # SUMMARY BY REGION
    # ------------------------------------

    summary = (
        df.groupby("Region")
        .size()
        .reset_index(
            name="Number_of_Mines"
        )
        .sort_values(
            "Number_of_Mines",
            ascending=False
        )
    )

    summary.to_excel(
        writer,
        sheet_name="Regional_Summary",
        index=False
    )

    # ------------------------------------
    # COLUMN WIDTHS
    # ------------------------------------

    for sheet_name in writer.sheets:

        worksheet = writer.sheets[
            sheet_name
        ]

        for column_cells in worksheet.columns:

            max_length = 0

            column_letter = (
                column_cells[0].column_letter
            )

            for cell in column_cells:

                try:

                    value_length = len(
                        str(cell.value)
                    )

                    max_length = max(
                        max_length,
                        value_length
                    )

                except:

                    pass

            worksheet.column_dimensions[
                column_letter
            ].width = min(
                max_length + 2,
                60
            )


# ============================================================
# FINAL REPORT
# ============================================================

print("\n========================================")
print("SCRAPING FINISHED")
print("========================================\n")

print(
    f"Regions found: {len(region_links)}"
)

print(
    f"Unique mine pages found: "
    f"{len(all_mines)}"
)

print(
    f"Mine records scraped: "
    f"{len(df)}"
)

print(
    f"\nExcel file: {OUTPUT_FILE}"
)

print("\nRegional summary:")

print(summary.to_string(index=False))