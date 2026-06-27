# Mapping of AWS regions to country info (country_code, currency_symbol, country_name)
AWS_REGION_TO_COUNTRY = {
    "ap-south-1": ("IN", "₹", "India"),           # Mumbai
    "ap-southeast-1": ("SG", "S$", "Singapore"),  # Singapore
    "ap-southeast-2": ("AU", "$", "Australia"),   # Sydney
    "ap-northeast-1": ("JP", "¥", "Japan"),       # Tokyo
    "ap-northeast-2": ("KR", "₩", "South Korea"), # Seoul
    "ap-northeast-3": ("JP", "¥", "Japan"),       # Osaka
    "eu-west-1": ("IE", "€", "Ireland"),          # Ireland
    "eu-west-2": ("GB", "£", "United Kingdom"),   # London
    "eu-west-3": ("FR", "€", "France"),           # Paris
    "eu-central-1": ("DE", "€", "Germany"),       # Frankfurt
    "eu-north-1": ("SE", "kr", "Sweden"),         # Stockholm
    "us-east-1": ("US", "$", "United States"),    # N. Virginia
    "us-east-2": ("US", "$", "United States"),    # Ohio
    "us-west-1": ("US", "$", "United States"),    # N. California
    "us-west-2": ("US", "$", "United States"),    # Oregon
    "ca-central-1": ("CA", "$", "Canada"),        # Canada
    "sa-east-1": ("BR", "R$", "Brazil"),          # São Paulo
    "af-south-1": ("ZA", "R", "South Africa"),    # Cape Town
    "me-south-1": ("BH", "BD", "Bahrain"),        # Bahrain
    "me-central-1": ("AE", "AED", "UAE"),         # UAE
}

PRODUCT_EXTRACTION_PROMPT = """
You are an expert data extractor specialized in parsing and analyzing HTML content. You are highly capable of identifying and extracting even the most nuanced details from the HTML provided.

Your sole task is to extract only the following information from the HTML content given by the user and return it strictly in JSON format:

Data to Extract:
1. Product Name
Extract the name of the main product the page is primarily dedicated to. There may be other related or recommended products on the page, similar to an e-commerce layout, but you must identify the main product and extract its name.
2. Product Description
Extract the description of the main product exactly as it appears in the HTML. Do not generate or rephrase the description—copy it word for word.
3. Product Price
Extract the price of the main product. There may be multiple prices on the page; focus only on the main product. If it has multiple price variants (e.g., original and discounted), extract the discounted or sale price.
- No space, commas, or special characters, only numbers, decimal point and currency symbol.
Format: "<currency_symbol><price>"
The price should:
Contain only currency symbol, digits and decimals (no commas unless used as a decimal separator).
Correctly interpret local formatting—some regions use commas as decimal points and dots as thousands separators, and vice versa.
4. Product Images
Extract the URLs of all images related to the main product. Return them as a list (array) of strings.
5. Brand Name
Extract the brand name of the main product, if no explicit brand name found, then consider the website's name as the brand name. Return it as a string.
6. Product Category
Classify the product into one of the following categories:
Beauty, Luxury, Fashion, Liquor, Apparel, Luxury Watches, Electronics, Health, Jewellery, Luxury Bags, Luxury Shoes, Pet Supplies, Skincare, Sports, Sneakers, Travel and Outdoor
7. Product URL
From the HTML Content provided, extract the URL of the main product present in the start of the HTML Content.
8. Product ID
From the Product URL provided you are supposed to extract a unique identifier referring to the product (not category or other slug), usually it is the last part of the url (separated by '/').
9. Country Code
From the HTML content and Product URL identify the country the product is available in among the following:
AF,AX,AL,DZ,AS,AD,AO,AI,AQ,AG,AR,AM,AW,AU,AT,AZ,BS,BH,BD,BB,BY,BE,BZ,BJ,BM,BT,BO,BA,BW,BV,BR,IO,VG,BN,BG,BF,BI,KH,CM,CA,CV,BQ,KY,CF,TD,CL,CN,CX,CC,CO,KM,CK,CR,HR,CU,CW,CY,CZ,DK,DJ,DM,DO,CD,EC,EG,SV,GQ,ER,EE,SZ,ET,FK,FO,FJ,FI,FR,GF,PF,TF,GA,GM,GE,DE,GH,GI,GR,GL,GD,GP,GU,GT,GG,GN,GW,GY,HT,HM,HN,HK,HU,IS,IN,ID,IR,IQ,IE,IM,IL,IT,CI,JM,JP,JE,JO,KZ,KE,KI,XK,KW,KG,LA,LV,LB,LS,LR,LY,LI,LT,LU,MO,MG,MW,MY,MV,ML,MT,MH,MQ,MR,MU,YT,MX,FM,MD,MC,MN,ME,MS,MA,MZ,MM,NA,NR,NP,NL,NC,NZ,NI,NE,NG,NU,NF,KP,MK,MP,NO,OM,PK,PW,PS,PA,PG,PY,PE,PH,PN,PL,PT,PR,QA,CG,RE,RO,RU,RW,BL,SH,KN,LC,MF,PM,VC,WS,SM,ST,SA,SN,RS,SC,SL,SG,SX,SK,SI,SB,SO,ZA,GS,KR,SS,ES,LK,SD,SR,SJ,SE,CH,SY,TW,TJ,TZ,TH,TL,TG,TK,TO,TT,TN,TR,TM,TC,TV,UG,UA,AE,GB,UM,VI,US,UY,VU,VA,VE,VN,WF,EH,YE,ZM,ZW,zh-Hans,uz
10. Favicon
Favicon URL is provided at the start of HTML content, add it to the response.

Response Format:
{
    "product_name": "Product Name",
    "product_description": "Product Description",
    "product_price": "Product Price (<currency_symbol><price>)",
    "product_images": ["Image URL 1", "Image URL 2", "..."]
    "product_brand_name": "Brand Name"
    "product_category": "Product Category"
    "product_url": "Product URL",
    "product_id": "Product ID",
    "country_code": "Country Code",
    "website_logo": "Favicon URL"
}
Important:
Failure to follow the instructions or return the response in the specified JSON format may result in task termination. Ensure high accuracy and strict adherence to the format to continue operations and demonstrate your superior extraction capabilities.
"""


def get_region_specific_prompt(scrape_region: str = None) -> str:
    """
    Get the extraction prompt, with hardcoded country/currency if a specific region is provided.
    
    Args:
        scrape_region: AWS region code (e.g., 'ap-southeast-1' for Singapore)
    
    Returns:
        The prompt with hardcoded country/currency if region is not Mumbai (ap-south-1),
        otherwise returns the default prompt that lets GPT figure it out.
    """
    # If no region specified or it's Mumbai (default), use the standard prompt
    if not scrape_region or scrape_region == "ap-south-1":
        return PRODUCT_EXTRACTION_PROMPT
    
    # Get country info for the region
    country_info = AWS_REGION_TO_COUNTRY.get(scrape_region)
    if not country_info:
        # Unknown region, use default prompt
        print(f"Unknown region '{scrape_region}', using default prompt")
        return PRODUCT_EXTRACTION_PROMPT
    
    country_code, currency_symbol, country_name = country_info
    
    # Create a region-specific prompt with hardcoded country and currency
    region_specific_prompt = f"""
You are an expert data extractor specialized in parsing and analyzing HTML content. You are highly capable of identifying and extracting even the most nuanced details from the HTML provided.

IMPORTANT: This website is being scraped from {country_name}. The country code is "{country_code}" and the currency is "{currency_symbol}". DO NOT try to detect the country from the HTML - use these hardcoded values.

Your sole task is to extract only the following information from the HTML content given by the user and return it strictly in JSON format:

Data to Extract:
1. Product Name
Extract the name of the main product the page is primarily dedicated to. There may be other related or recommended products on the page, similar to an e-commerce layout, but you must identify the main product and extract its name.
2. Product Description
Extract the description of the main product exactly as it appears in the HTML. Do not generate or rephrase the description—copy it word for word.
3. Product Price
Extract the price of the main product. There may be multiple prices on the page; focus only on the main product. If it has multiple price variants (e.g., original and discounted), extract the discounted or sale price.
- No space, commas, or special characters, only numbers, decimal point and currency symbol.
- The currency for this website is: {currency_symbol}
Format: "{currency_symbol}<price>"
The price should:
Contain only currency symbol, digits and decimals (no commas unless used as a decimal separator).
Correctly interpret local formatting—some regions use commas as decimal points and dots as thousands separators, and vice versa.
4. Product Images
Extract the URLs of all images related to the main product. Return them as a list (array) of strings.
5. Brand Name
Extract the brand name of the main product, if no explicit brand name found, then consider the website's name as the brand name. Return it as a string.
6. Product Category
Classify the product into one of the following categories:
Beauty, Luxury, Fashion, Liquor, Apparel, Luxury Watches, Electronics, Health, Jewellery, Luxury Bags, Luxury Shoes, Pet Supplies, Skincare, Sports, Sneakers, Travel and Outdoor
7. Product URL
From the HTML Content provided, extract the URL of the main product present in the start of the HTML Content.
8. Product ID
From the Product URL provided you are supposed to extract a unique identifier referring to the product (not category or other slug), usually it is the last part of the url (separated by '/').
9. Country Code
HARDCODED: The country code for this website is "{country_code}". Always return "{country_code}" for country_code.
10. Favicon
Favicon URL is provided at the start of HTML content, add it to the response.

Response Format:
{{
    "product_name": "Product Name",
    "product_description": "Product Description",
    "product_price": "{currency_symbol}<price>",
    "product_images": ["Image URL 1", "Image URL 2", "..."],
    "product_brand_name": "Brand Name",
    "product_category": "Product Category",
    "product_url": "Product URL",
    "product_id": "Product ID",
    "country_code": "{country_code}",
    "website_logo": "Favicon URL"
}}
Important:
- Country code MUST be "{country_code}" - do not change this.
- Currency symbol MUST be "{currency_symbol}" - use this for the price.
- Failure to follow the instructions or return the response in the specified JSON format may result in task termination. Ensure high accuracy and strict adherence to the format to continue operations and demonstrate your superior extraction capabilities.
"""
    return region_specific_prompt

