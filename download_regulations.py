import requests
from urllib.parse import urljoin
from pathlib import Path

BASE_URL = "https://stg-old.fssai.gov.in"
REGULATIONS_PAGE = "https://stg-old.fssai.gov.in/cms/food-safety-and-standards-regulations.php"

OUTPUT_DIR = Path(__file__).resolve().parent / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)

REGULATIONS = [
    {
        "num": 1,
        "name": "Licensing_and_Registration_of_Food_Businesses",
        "regulation_url": "/upload/uploadfiles/files/Licensing_Regulations.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Licensing_Regulations_04_08_2021.pdf",
    },
    {
        "num": 2,
        "name": "Food_Products_Standards_and_Food_Additives",
        "regulation_url": "/upload/uploadfiles/files/Food_Additives_Regulations.pdf",
        "compendium_url": "/cms/Compendium-FSS-FPS-FA.php",
    },
    {
        "num": 3,
        "name": "Prohibition_and_Restriction_of_Sales",
        "regulation_url": "/upload/uploadfiles/files/Prohibition_Regulations.pdf",
        "compendium_url": "/upload/uploadfiles/files/Comp_Prohibition%20and%20Restrcition%20of%20sales%20XI_01042025.pdf",
    },
    {
        "num": 4,
        "name": "Contaminants_Toxins_and_Residues",
        "regulation_url": "/upload/uploadfiles/files/Contaminants_Regulations.pdf",
        "compendium_url": None,
    },
    {
        "num": 5,
        "name": "Laboratory_and_Sampling_Analysis",
        "regulation_url": "/upload/uploadfiles/files/Lab_Sample_Regulations.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Lab_Sample_Regulations_04_03_2021.pdf",
    },
    {
        "num": 6,
        "name": "Health_Supplements_Nutraceuticals_etc",
        "regulation_url": "/upload/uploadfiles/files/Nutraceuticals_Regulations.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Nutra_29_09_2021.pdf",
    },
    {
        "num": 7,
        "name": "Food_Recall_Procedure",
        "regulation_url": "/upload/uploadfiles/files/Food_Recall_Regulations.pdf",
        "compendium_url": None,
    },
    {
        "num": 8,
        "name": "Import",
        "regulation_url": "/upload/uploadfiles/files/Food_Import_Regulations.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Import_VII_06_11_2025.pdf",
    },
    {
        "num": 9,
        "name": "Approval_for_Non_Specific_Food_and_Food_Ingredients",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_NonSpecified_Food_Ingredients_15_09_2017.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_FSS_NFS_FA_17_10_2022.pdf",
    },
    {
        "num": 10,
        "name": "Organic_Food",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Organic_Food_04_01_2017.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Organic_Food_05_06_2022.pdf",
    },
    {
        "num": 11,
        "name": "Alcoholic_Beverages",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Alcoholic_Beverages_05_04_2018.pdf",
        "compendium_url": "/upload/uploadfiles/files/Comp_Alcoholic_Beverages_V_04_12_2025.pdf",
    },
    {
        "num": 12,
        "name": "Fortification_of_Food",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Food_Fortification_10_08_2018.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Food_Fortification_Regulations_05_06_2022.pdf",
    },
    {
        "num": 13,
        "name": "Food_Safety_Auditing",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Food_Safety_Auditing_07_09_2018.pdf",
        "compendium_url": None,
    },
    {
        "num": 14,
        "name": "Recognition_and_Notification_of_Laboratories",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Labs_16_11_2018.pdf",
        "compendium_url": None,
    },
    {
        "num": 15,
        "name": "Advertising_and_Claims",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Advertising_Claims_27_11_2018.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Advertising_Claims_Regulations_14_12_2022.pdf",
    },
    {
        "num": 16,
        "name": "Packaging",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Packaging_03_01_2019.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Packaging_V_%2002-04-2025.pdf",
    },
    {
        "num": 17,
        "name": "Recovery_and_Distribution_of_Surplus_Food",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Surplus_Food_06_08_2019.pdf",
        "compendium_url": None,
    },
    {
        "num": 18,
        "name": "Safe_Food_and_Balanced_Diets_for_Children_in_School",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_Safe_Food_Children_07_09_2020.pdf",
        "compendium_url": None,
    },
    {
        "num": 19,
        "name": "Foods_for_Infant_Nutrition",
        "regulation_url": "/upload/notifications/2020/12/5fd719575c4d5Gazette_Notification_Food_Infant_14_12_2020.pdf",
        "compendium_url": "/upload/uploadfiles/files/Comp_IFR_VERSION-II_04_01_2024.pdf",
    },
    {
        "num": 20,
        "name": "Labelling_and_Display",
        "regulation_url": "/upload/notifications/2020/12/5fd87c6a0f6adGazette_Notification_Labelling_Display_14_12_2020.pdf",
        "compendium_url": "/upload/uploadfiles/files/Comp_Labelling%20Display_Version%20VIII_09_09_2025.pdf",
    },
    {
        "num": 21,
        "name": "Ayurveda_Aahara",
        "regulation_url": "/upload/notifications/2022/05/62789a20b54bdGazette_Notification_Ayurveda_Aahara_09_05_2022.pdf",
        "compendium_url": None,
    },
    {
        "num": 22,
        "name": "Vegan_Foods",
        "regulation_url": "/upload/notifications/2022/06/62ac3f9dba33cGazette_Notification_Vegan_Food_17_06_2022.pdf",
        "compendium_url": None,
    },
    {
        "num": 23,
        "name": "Transaction_of_Business_at_Meetings",
        "regulation_url": "/upload/uploadfiles/files/Notification_of_Regulations_on_Transaction_of_Business.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_Transaction_of_Businesses_VersionII(27_03_2023)(1).pdf",
    },
    {
        "num": 24,
        "name": "Procedure_for_Transaction_of_Business_of_CAC",
        "regulation_url": "/upload/uploadfiles/files/Notification_of_Regulations_on_Procedure_Transaction_of_Business.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_CAC_Version_I_29_09_2021.pdf",
    },
    {
        "num": 25,
        "name": "Salary_Allowances_and_Conditions_of_Service",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_22_08_2013.pdf",
        "compendium_url": None,
    },
    {
        "num": 26,
        "name": "Transaction_of_Business_Scientific_Committee_Panel",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_SC_SP_14_12_2016.pdf",
        "compendium_url": "/upload/uploadfiles/files/Compendium_SCSP_Version_I_29_09_2021.pdf",
    },
    {
        "num": 27,
        "name": "Recruitment_and_Appointment",
        "regulation_url": "/upload/uploadfiles/files/Gazette_Notification_RR_12_10_2018.pdf",
        "compendium_url": None,
    },
    {
        "num": 28,
        "name": "Financial_Regulations",
        "regulation_url": "/upload/uploadfiles/files/order_regulation.pdf",
        "compendium_url": None,
    },
]

def download_file(url, dest_path):
    try:
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"Downloaded: {dest_path.name} ({dest_path.stat().st_size / 1024:.1f} KB)")
        return True
    except Exception as e:
        print(f"Failed to download {url}: {e}")
        return False

def main():
    for reg in REGULATIONS:
        reg_dir = OUTPUT_DIR / f"{reg['num']:02d}_{reg['name']}"
        reg_dir.mkdir(exist_ok=True)
        
        # Download Regulation PDF
        if reg['regulation_url']:
            reg_url = urljoin(BASE_URL, reg['regulation_url'])
            dest = reg_dir / "Regulation.pdf"
            print(f"\n[{reg['num']:02d}] {reg['name']}")
            print(f"  Downloading Regulation...")
            download_file(reg_url, dest)
        
        # Download Compendium PDF
        if reg['compendium_url']:
            comp_url = urljoin(BASE_URL, reg['compendium_url'])
            dest = reg_dir / "Compendium.pdf"
            print(f"  Downloading Compendium...")
            download_file(comp_url, dest)
        else:
            print(f"  No Compendium available")

if __name__ == "__main__":
    main()
