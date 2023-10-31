import pandas as pd
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import logging
import traceback
import numpy as np
import itertools

GM_WEBPAGE = 'https://www.google.com/maps/'
MAX_WAIT = 10
MAX_RETRY = 5
MAX_SCROLLS = 40

class GoogleMapsScraper:

    def __init__(self, debug=False):
        print("Initializing GoogleMapsScraper...")
        self.debug = debug
        self.driver = self.__get_driver()
        self.logger = self.__get_logger()
        print("GoogleMapsScraper initialized successfully.")

    def __enter__(self):
        print("Entering GoogleMapsScraper context.")
        return self

    def __exit__(self, exc_type, exc_value, tb):
        print("Exiting GoogleMapsScraper context.")
        if exc_type is not None:
            print("Exception encountered:")
            traceback.print_exception(exc_type, exc_value, tb)

        print("Closing and quitting driver.")
        self.driver.close()
        self.driver.quit()
        print("Driver closed and quit successfully.")

        return True

    def sort_by(self, url, ind):
        print(f"Starting sort_by")
        print("Attempting to navigate to URL...")
        self.driver.get(url)
        print("URL navigation successful.")
        
        cookie_click_result = self.__click_on_cookie_agreement()
        if cookie_click_result:
            print("Cookie agreement clicked successfully.")
        else:
            print("Failed to click cookie agreement or not found.")

        wait = WebDriverWait(self.driver, MAX_WAIT)
        self.__scroll()
        self.__expand_reviews()
        
        # open dropdown menu
        clicked = False
        tries = 0
        while not clicked and tries < MAX_RETRY:
            try:
                print("Attempting to click sorting button...")
                menu_bt = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@data-value=\'Sort\']')))
                menu_bt.click()

                clicked = True
                time.sleep(3)
                print("Sorting button clicked successfully.")
            except Exception as e:
                tries += 1
                print(f"Failed to click sorting button on attempt {tries}. Retrying...")
                self.logger.warn('Failed to click sorting button')

            # failed to open the dropdown
            if tries == MAX_RETRY:
                print("Failed to open the dropdown menu after maximum retries.")
                return -1

        print(f"Attempting to select sorting option index {ind}...")
        try:
            recent_rating_bt = self.driver.find_elements(By.XPATH, '//div[@role=\'menuitemradio\']')[ind]
            recent_rating_bt.click()
            print("Sorting option selected successfully.")
        except Exception as e:
            print(f"Failed to select sorting option index {ind}. Error: {e}")
            return -1

        # wait to load review (ajax call)
        time.sleep(5)
        print("Waiting for reviews to load after sorting...")

        return 0

    def get_places(self, keyword_list=None):
        print(f"Starting get_places")
        df_places = pd.DataFrame()
        search_point_url_list = self._gen_search_points_from_square(keyword_list=keyword_list)

        for i, search_point_url in enumerate(search_point_url_list):
            print(f"Processing search point URL: {search_point_url}")

            if (i+1) % 10 == 0:
                print(f"{i}/{len(search_point_url_list)}")
                df_places = df_places[['search_point_url', 'href', 'name', 'rating', 'num_reviews', 'close_time', 'other']]
                df_places.to_csv('output/places_wax.csv', index=False)

            try:
                print(f"Attempting to navigate to search point URL: {search_point_url}")
                self.driver.get(search_point_url)
                print("Navigation to search point URL successful.")
            except NoSuchElementException:
                print("Navigation failed. Restarting driver and retrying...")
                self.driver.quit()
                self.driver = self.__get_driver()
                self.driver.get(search_point_url)

            # scroll to load all (20) places into the page
            try:
                print("Attempting to scroll to load all places...")
                scrollable_div = self.find_element(By.CSS_SELECTOR, '.w6VYqd div.e07Vkf.kA9KIf')
                
                #.driver.find_element(By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.ecceSd > div[aria-label*='Results for']")
                for j in range(10):
                    self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
                print("Scrolling successful.")
            except Exception as e:
                print(f"Error during scrolling: {e}")

            # Get places names and href
            time.sleep(2)
            print("Parsing page content...")
            response = BeautifulSoup(self.driver.page_source, 'html.parser')
            div_places = response.select('div[jsaction] > a[href]')

            for div_place in div_places:
                place_info = {
                    'search_point_url': search_point_url.replace('https://www.google.com/maps/search/', ''),
                    'href': div_place['href'],
                    'name': div_place['aria-label']
                }

                df_places = df_places.append(place_info, ignore_index=True)

            print(f"Total places found so far: {len(df_places)}")

            # TODO: implement click to handle > 20 places

        df_places = df_places[['search_point_url', 'href', 'name']]
        df_places.to_csv('output/places_wax.csv', index=False)
        print("Places data saved to CSV.")

    def get_reviews(self, offset):
        print(f"Starting get_reviews")
        print(f"Attempting to scroll to load reviews from offset: {offset}")
        # scroll to load reviews
        # self.__scroll()
        self.scroll_reviews()

        # wait for other reviews to load (ajax)
        wait_time = 4 + (3 if offset > 0 else 0)
        time.sleep(wait_time)

        print("Attempting to expand review text...")
        # expand review text
        # self.__expand_reviews()
        self.__expand_reviews_text()
        


        print("Parsing reviews...")
        # parse reviews
        response = BeautifulSoup(self.driver.page_source, 'html.parser')
        # print(f'print response {response}')
        with open('response.html', 'w', encoding='utf-8') as file:
            file.write(str(response))
            print('saved response.html')
        # TODO: Subject to changes
        rblock = response.select('div.jftiEf.fontBodyMedium')

        #response.find_all('div', class_='jftiEf fontBodyMedium ')
        # print(f'print rlock {rblock}')
        parsed_reviews = []
        for index, review in enumerate(rblock):
            if index >= offset:
                print(f"Processing review {index}...")
                r = self.__parse(review)
                parsed_reviews.append(r)

                # logging to std out
                print(f"Review {index} details: {r}")

        print(f"Total reviews fetched: {len(parsed_reviews)}")
        return parsed_reviews


    # need to use different url wrt reviews one to have all info
    def get_account(self, url):
        print(f"Starting get_account")
        print(f"Accessing URL: {url}")
        self.driver.get(url)

        print("Attempting to click on cookie agreement...")
        self.__click_on_cookie_agreement()

        # ajax call also for this section
        time.sleep(2)

        print("Parsing page source...")
        resp = BeautifulSoup(self.driver.page_source, 'html.parser')

        print("Parsing place data...")
        place_data = self.__parse_place(resp, url)

        print(f"Place data fetched: {place_data}")
        return place_data


    def __parse(self, review):
        print(f"Starting __parse")
        item = {}

        try:
            # TODO: Subject to changes
            id_review = review['data-review-id']
            print("Successful id_review")
        except Exception as e:
            id_review = None
            print(f"Error parsing id_review: {e}")

        try:
            # TODO: Subject to changes
            username = review['aria-label']
            print("Successful username")
        except Exception as e:
            username = None
            print(f"Error parsing username: {e}")

        try:
            # TODO: Subject to changes
            review_text = self.__filter_string(review.find('span', class_='wiI7pd').text)
            print("Successful review_text")
        except Exception as e:
            review_text = None
            print(f"Error parsing review_text: {e}")

        try:
            # TODO: Subject to changes
            rating = float(review.find('span', class_='kvMYJc')['aria-label'].split(' ')[0])
            print("Successful rating")
        except Exception as e:
            rating = None
            print(f"Error parsing rating: {e}")

        try:
            # TODO: Subject to changes
            relative_date = review.find('span', class_='rsqaWe').text
            print("Successful relative_date")
        except Exception as e:
            relative_date = None
            print(f"Error parsing relative_date: {e}")

        try:
            n_reviews = review.find('div', class_='RfnDt').text.split(' ')[3]
            print("Successful n_reviews")
        except Exception as e:
            n_reviews = 0
            print(f"Error parsing n_reviews: {e}")

        try:
            user_url = review.find('button', class_='WEBjve')['data-href']
            print("Successful user_url")
        except Exception as e:
            user_url = None
            print(f"Error parsing user_url: {e}")
        

        # Additional parsing for categories and ratings
        try:
            print("Getting additional review info")
            r_additional_blocks = review.select('div[jslog="127691"] div.PBK6be')
            r_additional = []
            if r_additional_blocks:
                for block in r_additional_blocks:
                    r_additional_text = block.get_text(separator=" ", strip=True)
                    if r_additional_text:
                        r_additional.append(r_additional_text)
            print("Successful parsed additional review info")
        except Exception as e:
            r_additional = []
            print(f"Error parsing additional review info: {e}")

        item['id_review'] = id_review
        item['caption'] = review_text

        # depends on language, which depends on geolocation defined by Google Maps
        # custom mapping to transform into date should be implemented
        item['relative_date'] = relative_date

        # store datetime of scraping and apply further processing to calculate
        # correct date as retrieval_date - time(relative_date)
        item['retrieval_date'] = datetime.now()
        item['rating'] = rating
        item['username'] = username
        item['n_review_user'] = n_reviews
        #item['n_photo_user'] = n_photos  ## not available anymore
        item['url_user'] = user_url
        item['r_additional'] = r_additional 
        ## print(f"Parsed review item: {item}")

        return item

    def __parse_place(self, response, url):
        print(f"Starting __parse_place")
        place = {}

        try:
            place['name'] = response.find('h1', class_='DUwDvf lfPIob').text.strip()
            print("Successfully")
        except Exception as e:
            place['name'] = None
            print(f"Error parsing name: {e}")

        try:
            place['overall_rating'] = float(response.find('div', class_='F7nice').find('span', class_='ceNzKf')['aria-label'].split(' ')[0])
            print("Successfully")
        except Exception as e:
            place['overall_rating'] = None
            print(f"Error parsing overall_rating: {e}")

        try:
            place['n_reviews'] = int(response.find('div', class_='F7nice').text.split('(')[1].replace(',', '').replace(')', ''))
            print("Successfully")
        except Exception as e:
            place['n_reviews'] = 0
            print(f"Error parsing n_reviews: {e}")

        try:
            place['n_photos'] = int(response.find('div', class_='YkuOqf').text.replace('.', '').replace(',','').split(' ')[0])
            print("Successfully")
        except Exception as e:
            place['n_photos'] = 0
            print(f"Error parsing n_photos: {e}")

        try:
            place['category'] = response.find('button', jsaction='pane.rating.category').text.strip()
            print("Successfully")
        except Exception as e:
            place['category'] = None
            print(f"Error parsing category: {e}")

        try:
            place['description'] = response.find('div', class_='PYvSYb').text.strip()
            print("Successfully")
        except Exception as e:
            place['description'] = None
            print(f"Error parsing description: {e}")

        b_list = response.find_all('div', class_='Io6YTe fontBodyMedium kR99db')
        try:
            place['address'] = b_list[0].text
            print("Successfully")
        except Exception as e:
            place['address'] = None
            print(f"Error parsing address: {e}")

        # Store the remaining details generically with error handling, as telephone, website vary in location and can not be reliably found using [n]
        for i in range(1, len(b_list)):
            try:
                place[f'detail_{i+1}'] = b_list[i].text
                print("Successfully")
            except Exception as e:
                place[f'detail_{i+1}'] = None
                print(f"Error parsing detail_{i+1}: {e}")

        try:
            place['opening_hours'] = response.find('div', class_='t39EBf GUrTXd')['aria-label'].replace('\u202f', ' ')
            print("Successfully")
        except Exception as e:
            place['opening_hours'] = None
            print(f"Error parsing opening_hours: {e}")

        place['url'] = url

        try:
            lat, long, z = url.split('/')[6].split(',')
            print("Successfully")
            place['lat'] = lat[1:]
            place['long'] = long
        except Exception as e:
            print(f"Error parsing latitude and longitude: {e}")

        print(f"Parsed place data: {place}")
        return place


    def _gen_search_points_from_square(self, keyword_list=None):
        print(f"Starting _gen_search_points_from_square")
        # TODO: Generate search points from corners of square
        print("Generating search points from square...")

        keyword_list = [] if keyword_list is None else keyword_list

        square_points = pd.read_csv('input/square_points.csv')

        cities = square_points['city'].unique()

        search_urls = []

        for city in cities:
            print(f"Processing city: {city}")

            df_aux = square_points[square_points['city'] == city]
            latitudes = df_aux['latitude'].unique()
            longitudes = df_aux['longitude'].unique()
            coordinates_list = list(itertools.product(latitudes, longitudes, keyword_list))

            search_urls += [f"https://www.google.com/maps/search/{coordinates[2]}/@{str(coordinates[1])},{str(coordinates[0])},{str(15)}z"
                            for coordinates in coordinates_list]

        print(f"Successfully generated {len(search_urls)} search URLs.")
        return search_urls

    # expand review description
    def __expand_reviews(self):
        print(f"Starting __expand_reviews")
        # use XPath to load complete reviews
        links = self.driver.find_elements(By.CSS_SELECTOR, 'button.M77dve[aria-label^="More reviews"]')
        for l in links:
            l.click()
        time.sleep(2)
        print("Successfully expanded reviews.")

    def __expand_reviews_text(self):
        # Find all review blocks
        print('starting __expand_reviews_text')
        review_blocks = self.driver.find_elements(By.CSS_SELECTOR, 'div.jftiEf.fontBodyMedium')
        print('starting to click more button')
        # Iterate through each review block
        for review_block in review_blocks:
            try:
                # Within each review block, find the "More" button
                more_button = review_block.find_element(By.CSS_SELECTOR, 'button.w8nwRe.kyuRq')
                # Click the "More" button if found
                more_button.click()
                print("Successfully expanded a review.")
            except NoSuchElementException:
                # If the "More" button is not found, continue to the next review block
                continue
        


    def __scroll(self):
        print(f"Starting __scroll")
        scrollable_div = self.driver.find_element(By.CSS_SELECTOR, '.w6VYqd div.e07Vkf.kA9KIf')
        self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
        print("Successfully scrolled")

    def scroll_reviews(self):
        print(f"Starting scroll_reviews")
        try:
            # Locating the parent element with class 'w6VYqd'
            parent_div = self.driver.find_element(By.CSS_SELECTOR, '.w6VYqd')
            # Within the parent, locating the scrollable div with the specified classes
            scrollable_div = parent_div.find_element(By.CSS_SELECTOR, '.m6QErb.DxyBCb.kA9KIf.dS8AEf')
            # Scrolling the element
            self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
            print("Successfully scrolled in scroll_reviews")
        except Exception as e:
            print(f"Error in scroll_reviews: {e}")

    def __get_logger(self):
        print(f"Starting __get_logger")
        print("Initializing logger...")
        # create logger
        logger = logging.getLogger('googlemaps-scraper')
        logger.setLevel(logging.DEBUG)

        # create console handler and set level to debug
        fh = logging.FileHandler('gm-scraper.log')
        fh.setLevel(logging.DEBUG)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # add formatter to ch
        fh.setFormatter(formatter)

        # add ch to logger
        logger.addHandler(fh)

        print("Logger successfully initialized.")
        return logger

    def __get_driver(self, debug=False):
        print(f"Starting __get_driver")
        print("Initializing ChromeDriver...")
        # Specify the path to the Chrome Beta binary
        chrome_binary_path = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"

        # Specify the path to the ChromeDriver executable for Chrome Beta
        driver_path = "/Users/jongarcia/codeup-data-science/googlemaps-scraper/chromedriver-mac-x64 BETA/chromedriver"

        # Create a ChromeOptions object
        options = Options()

        # Set the binary location to Chrome Beta
        options.binary_location = chrome_binary_path

        if not self.debug:
            options.add_argument("--headless")
        else:
            options.add_argument("--window-size=1366,768")

        options.add_argument("--disable-notifications")
        options.add_argument("--accept-lang=en-GB")

        # Create a Service object with the ChromeDriver path
        service = Service(driver_path)

        # Create a ChromeDriver with the specified options and executable path
        input_driver = webdriver.Chrome(service=service, options=options)

        # click on google agree button so we can continue (not needed anymore)
        input_driver.get(GM_WEBPAGE)

        print("ChromeDriver successfully initialized.")
        return input_driver

    # cookies agreement click
    def __click_on_cookie_agreement(self):
        print(f"Starting __click_on_cookie_agreement")
        print("Clicking on cookie agreement...")
        try:
            agree = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "Reject all")]')))
            agree.click()

            # back to the main page
            # self.driver.switch_to_default_content()

            print("Successfully clicked on cookie agreement.")
            return True
        except:
            print("Failed to click on cookie agreement.")
            return False

    # util function to clean special characters
    def __filter_string(self, str):
        print(f"Starting __filter_string")
        print(f"Cleaning string")
        strOut = str.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
        print(f"Cleaned string: {strOut}")
        return strOut

