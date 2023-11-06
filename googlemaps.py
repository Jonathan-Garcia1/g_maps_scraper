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
import requests

from stem import Signal
from stem.control import Controller

from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
import logging
import traceback
import numpy as np
import itertools

import env
import os

GM_WEBPAGE = 'https://www.google.com/maps/'
MAX_WAIT = 10
MAX_RETRY = 5
MAX_SCROLLS = 40

class GoogleMapsScraper:

    def __init__(self, debug=False):
        self.debug = debug
        logging.debug("Initializing GoogleMapsScraper...")
        self.driver = self.__get_driver()
        self.logger = self.__get_logger()
        logging.debug("GoogleMapsScraper initialized successfully.")

    def renew_tor_ip(self):
        with Controller.from_port(port=9051) as controller:
            controller.authenticate(password= env.torp)  # Use the password you set
            controller.signal(Signal.NEWNYM)
        # Check if IP has changed
        new_ip = self.__get_ip_with_tor()
        if new_ip != self.last_masked_ip:
            print("Tor IP successfully renewed.")
            self.last_masked_ip = new_ip
        else:
            print("Warning: Tor IP did not change after renewal.")

    def __get_ip_without_tor(self):
        response = requests.get('http://httpbin.org/ip')
        ip_without_tor = response.json()['origin']
        logging.debug("IP without Tor:", ip_without_tor)
        return ip_without_tor

    def __get_ip_with_tor(self):
        self.driver.get('http://httpbin.org/ip')
        response_text = self.driver.find_element(By.TAG_NAME, 'pre').text
        ip_with_tor = eval(response_text)['origin']
        logging.debug("IP with Tor:", ip_with_tor)
        return ip_with_tor

    def test_tor_connection(self):
        logging.debug("Testing Tor connection...")

        # Get IP without Tor
        ip_without_tor = self.__get_ip_without_tor()

        # Get IP with Tor
        ip_with_tor = self.__get_ip_with_tor()

        # Store the initial masked IP
        self.last_masked_ip = ip_with_tor

        # Check if the IP addresses are different
        if ip_without_tor != ip_with_tor:
            print("IP masking successful: Your IP address is being masked by Tor.")
            return True
        else:
            print("IP masking unsuccessful: Your IP address is not being masked by Tor.")
            return False



    def __enter__(self):
        logging.debug("Entering GoogleMapsScraper context.")
        return self

    def __exit__(self, exc_type, exc_value, tb):
        logging.debug("Exiting GoogleMapsScraper context.")
        if exc_type is not None:
            logging.debug("Exception encountered:")
            traceback.print_exception(exc_type, exc_value, tb)

        # logging.debug("Closing and quitting driver.")
        # self.driver.close()
        # self.driver.quit()
        logging.debug("Driver closed and quit successfully.")

        return True

    def sort_by(self, url, ind):
        logging.debug(f"Starting sort_by")
        logging.debug("Attempting to navigate to URL...")
        self.driver.get(url)
        logging.debug("URL navigation successful.")
        
        cookie_click_result = self.__click_on_cookie_agreement()
        if cookie_click_result:
            logging.debug("Cookie agreement clicked successfully.")
        else:
            logging.debug("Failed to click cookie agreement or not found.")

        wait = WebDriverWait(self.driver, MAX_WAIT)
        self.__scroll()
        self.__expand_reviews()
        
        # open dropdown menu
        clicked = False
        tries = 0
        while not clicked and tries < MAX_RETRY:
            try:
                logging.debug("Attempting to click sorting button...")
                menu_bt = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@data-value=\'Sort\']')))
                menu_bt.click()

                clicked = True
                time.sleep(3)
                logging.debug("Sorting button clicked successfully.")
            except Exception as e:
                tries += 1
                logging.debug(f"Failed to click sorting button on attempt {tries}. Retrying...")
                self.logger.warn('Failed to click sorting button')

            # failed to open the dropdown
            if tries == MAX_RETRY:
                logging.debug("Failed to open the dropdown menu after maximum retries.")
                return -1

        logging.debug(f"Attempting to select sorting option index {ind}...")
        try:
            recent_rating_bt = self.driver.find_elements(By.XPATH, '//div[@role=\'menuitemradio\']')[ind]
            recent_rating_bt.click()
            logging.debug("Sorting option selected successfully.")
        except Exception as e:
            logging.debug(f"Failed to select sorting option index {ind}. Error: {e}")
            return -1

        # wait to load review (ajax call)
        time.sleep(5)
        logging.debug("Waiting for reviews to load after sorting...")

        return 0

    def get_places(self, keyword_list=None):
        logging.debug(f"Starting get_places")
        df_places = pd.DataFrame()
        search_point_url_list = self._gen_search_points_from_square(keyword_list=keyword_list)

        for i, search_point_url in enumerate(search_point_url_list):
            logging.debug(f"Processing search point URL: {search_point_url}")

            if (i+1) % 10 == 0:
                logging.debug(f"{i}/{len(search_point_url_list)}")
                df_places = df_places[['search_point_url', 'href', 'name', 'rating', 'num_reviews', 'close_time', 'other']]
                df_places.to_csv('output/places_wax.csv', index=False)

            try:
                logging.debug(f"Attempting to navigate to search point URL: {search_point_url}")
                self.driver.get(search_point_url)
                logging.debug("Navigation to search point URL successful.")
            except NoSuchElementException:
                logging.debug("Navigation failed. Restarting driver and retrying...")
                os.system('afplay /System/Library/Sounds/Ping.aiff')
                time.sleep(30)
                self.driver.quit()
                self.driver = self.__get_driver()
                self.driver.get(search_point_url)

            # scroll to load all (20) places into the page
            try:
                logging.debug("Attempting to scroll to load all places...")
                scrollable_div = self.find_element(By.CSS_SELECTOR, '.w6VYqd div.e07Vkf.kA9KIf')
                
                #.driver.find_element(By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.ecceSd > div[aria-label*='Results for']")
                for j in range(10):
                    self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
                logging.debug("Scrolling successful.")
            except Exception as e:
                logging.debug(f"Error during scrolling: {e}")

            # Get places names and href
            time.sleep(2)
            logging.debug("Parsing page content...")
            response = BeautifulSoup(self.driver.page_source, 'html.parser')
            div_places = response.select('div[jsaction] > a[href]')

            for div_place in div_places:
                place_info = {
                    'search_point_url': search_point_url.replace('https://www.google.com/maps/search/', ''),
                    'href': div_place['href'],
                    'name': div_place['aria-label']
                }

                df_places = df_places.append(place_info, ignore_index=True)

            logging.debug(f"Total places found so far: {len(df_places)}")

            # TODO: implement click to handle > 20 places

        df_places = df_places[['search_point_url', 'href', 'name']]
        df_places.to_csv('output/places_wax.csv', index=False)
        logging.debug("Places data saved to CSV.")

    def get_reviews(self, offset):
        logging.debug(f"Starting get_reviews")
        logging.debug(f"Attempting to scroll to load reviews from offset: {offset}")
        # scroll to load reviews
        # self.__scroll()
        self.scroll_reviews()

        # wait for other reviews to load (ajax)
        wait_time = 4 + (3 if offset > 0 else 0)
        time.sleep(wait_time)

        logging.debug("Attempting to expand review text...")
        # expand review text
        # self.__expand_reviews()
        self.__expand_reviews_text()
        


        logging.debug("Parsing expanded reviews...")
        # parse reviews
        response = BeautifulSoup(self.driver.page_source, 'html.parser')
        # # logging.debug(f'print response {response}')
        # with open('response.html', 'w', encoding='utf-8') as file:
        #     file.write(str(response))
        #     logging.debug('saved response.html')
        # TODO: Subject to changes
        rblock = response.select('div.jftiEf.fontBodyMedium')

        #response.find_all('div', class_='jftiEf fontBodyMedium ')
        # logging.debug(f'print rlock {rblock}')
        parsed_reviews = []
        for index, review in enumerate(rblock):
            if index >= offset:
                logging.debug(f"Processing review {index}...")
                r = self.__parse(review)
                parsed_reviews.append(r)

                # logging to std out
                logging.debug(f"Review {index} details: {r}")

        logging.debug(f"Total reviews fetched: {len(parsed_reviews)}")
        return parsed_reviews


    # need to use different url wrt reviews one to have all info
    def get_account(self, url):
        logging.debug(f"Starting get_account")
        logging.debug(f"Accessing URL: {url}")
        self.driver.get(url)

        logging.debug("Attempting to click on cookie agreement...")
        self.__click_on_cookie_agreement()

        # ajax call also for this section
        time.sleep(2)

        logging.debug("Parsing page source...")
        resp = BeautifulSoup(self.driver.page_source, 'html.parser')

        logging.debug("Parsing place data...")
        place_data = self.__parse_place(resp, url)

        logging.debug(f"Place data fetched: {place_data}")
        return place_data


    def __parse(self, review):
        logging.debug(f"Starting __parse")
        item = {}

        try:
            # TODO: Subject to changes
            id_review = review['data-review-id']
            logging.debug("Successful id_review")
        except Exception as e:
            id_review = None
            logging.debug(f"Error parsing id_review: {e}")

        try:
            # TODO: Subject to changes
            username = review['aria-label']
            logging.debug("Successful username")
        except Exception as e:
            username = None
            logging.debug(f"Error parsing username: {e}")

        try:
            # TODO: Subject to changes
            review_text = self.__filter_string(review.find('span', class_='wiI7pd').text)
            logging.debug("Successful review_text")
        except Exception as e:
            review_text = None
            logging.debug(f"Error parsing review_text: {e}")

        try:
            # TODO: Subject to changes
            rating = float(review.find('span', class_='kvMYJc')['aria-label'].split(' ')[0])
            logging.debug("Successful rating")
        except Exception as e:
            rating = None
            logging.debug(f"Error parsing rating: {e}")

        try:
            # TODO: Subject to changes
            relative_date = review.find('span', class_='rsqaWe').text
            logging.debug("Successful relative_date")
        except Exception as e:
            relative_date = None
            logging.debug(f"Error parsing relative_date: {e}")

        try:
            n_reviews = review.find('div', class_='RfnDt').text.split(' ')[3]
            logging.debug("Successful n_reviews")
        except Exception as e:
            n_reviews = 0
            logging.debug(f"Error parsing n_reviews: {e}")

        try:
            user_url = review.find('button', class_='WEBjve')['data-href']
            logging.debug("Successful user_url")
        except Exception as e:
            user_url = None
            logging.debug(f"Error parsing user_url: {e}")
        

        # Additional parsing for categories and ratings
        try:
            logging.debug("Getting additional review info")
            r_additional_blocks = review.select('div[jslog="127691"] div.PBK6be')
            r_additional = []
            if r_additional_blocks:
                for block in r_additional_blocks:
                    r_additional_text = block.get_text(separator=" ", strip=True)
                    if r_additional_text:
                        r_additional.append(r_additional_text)
            logging.debug("Successful parsed additional review info")
        except Exception as e:
            r_additional = []
            logging.debug(f"Error parsing additional review info: {e}")

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
        ## logging.debug(f"Parsed review item: {item}")

        return item

    def __parse_place(self, response, url):
        logging.debug(f"Starting __parse_place")
        place = {}

        try:
            place['name'] = response.find('h1', class_='DUwDvf lfPIob').text.strip()
            logging.debug("Successfully")
        except Exception as e:
            place['name'] = None
            logging.debug(f"Error parsing name: {e}")

        try:
            place['overall_rating'] = float(response.find('div', class_='F7nice').find('span', class_='ceNzKf')['aria-label'].split(' ')[0])
            logging.debug("Successfully")
        except Exception as e:
            place['overall_rating'] = None
            logging.debug(f"Error parsing overall_rating: {e}")

        try:
            place['n_reviews'] = int(response.find('div', class_='F7nice').text.split('(')[1].replace(',', '').replace(')', ''))
            logging.debug("Successfully")
        except Exception as e:
            place['n_reviews'] = 0
            logging.debug(f"Error parsing n_reviews: {e}")

        try:
            place['n_photos'] = int(response.find('div', class_='YkuOqf').text.replace('.', '').replace(',','').split(' ')[0])
            logging.debug("Successfully")
        except Exception as e:
            place['n_photos'] = 0
            logging.debug(f"Error parsing n_photos: {e}")

        try:
            place['category'] = response.find('button', jsaction='pane.rating.category').text.strip()
            logging.debug("Successfully")
        except Exception as e:
            place['category'] = None
            logging.debug(f"Error parsing category: {e}")

        try:
            place['description'] = response.find('div', class_='PYvSYb').text.strip()
            logging.debug("Successfully")
        except Exception as e:
            place['description'] = None
            logging.debug(f"Error parsing description: {e}")

        b_list = response.find_all('div', class_='Io6YTe fontBodyMedium kR99db')
        try:
            place['address'] = b_list[0].text
            logging.debug("Successfully")
        except Exception as e:
            place['address'] = None
            logging.debug(f"Error parsing address: {e}")

        # Store the remaining details generically with error handling, as telephone, website vary in location and can not be reliably found using [n]
        for i in range(1, len(b_list)):
            try:
                place[f'detail_{i+1}'] = b_list[i].text
                logging.debug("Successfully")
            except Exception as e:
                place[f'detail_{i+1}'] = None
                logging.debug(f"Error parsing detail_{i+1}: {e}")

        try:
            place['opening_hours'] = response.find('div', class_='t39EBf GUrTXd')['aria-label'].replace('\u202f', ' ')
            logging.debug("Successfully")
        except Exception as e:
            place['opening_hours'] = None
            logging.debug(f"Error parsing opening_hours: {e}")

        place['url'] = url

        try:
            lat, long, z = url.split('/')[6].split(',')
            logging.debug("Successfully")
            place['lat'] = lat[1:]
            place['long'] = long
        except Exception as e:
            logging.debug(f"Error parsing latitude and longitude: {e}")

        logging.debug(f"Parsed place data: {place}")
        return place


    def _gen_search_points_from_square(self, keyword_list=None):
        logging.debug(f"Starting _gen_search_points_from_square")
        # TODO: Generate search points from corners of square
        logging.debug("Generating search points from square...")

        keyword_list = [] if keyword_list is None else keyword_list

        square_points = pd.read_csv('input/square_points.csv')

        cities = square_points['city'].unique()

        search_urls = []

        for city in cities:
            logging.debug(f"Processing city: {city}")

            df_aux = square_points[square_points['city'] == city]
            latitudes = df_aux['latitude'].unique()
            longitudes = df_aux['longitude'].unique()
            coordinates_list = list(itertools.product(latitudes, longitudes, keyword_list))

            search_urls += [f"https://www.google.com/maps/search/{coordinates[2]}/@{str(coordinates[1])},{str(coordinates[0])},{str(15)}z"
                            for coordinates in coordinates_list]

        logging.debug(f"Successfully generated {len(search_urls)} search URLs.")
        return search_urls

    # expand review description
    def __expand_reviews(self):
        logging.debug(f"Starting __expand_reviews")
        # use XPath to load complete reviews
        links = self.driver.find_elements(By.CSS_SELECTOR, 'button.M77dve[aria-label^="More reviews"]')
        for l in links:
            l.click()
        time.sleep(2)
        logging.debug("Successfully expanded reviews.")

    def __expand_reviews_text(self):
        # Find all review blocks
        logging.debug('starting __expand_reviews_text')
        review_blocks = self.driver.find_elements(By.CSS_SELECTOR, 'div.jftiEf.fontBodyMedium')
        logging.debug('starting to click more button')
        # Iterate through each review block
        for review_block in review_blocks:
            try:
                # Within each review block, find the "More" button
                more_button = review_block.find_element(By.CSS_SELECTOR, 'button.w8nwRe.kyuRq')
                # Click the "More" button if found
                more_button.click()
                logging.debug("Successfully expanded a review.")
            except NoSuchElementException:
                # If the "More" button is not found, continue to the next review block
                continue
        


    def __scroll(self):
        logging.debug(f"Starting __scroll")
        scrollable_div = self.driver.find_element(By.CSS_SELECTOR, '.w6VYqd div.e07Vkf.kA9KIf')
        self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
        logging.debug("Successfully scrolled")

    def scroll_reviews(self):
        logging.debug(f"Starting scroll_reviews")
        try:
            # Locating the parent element with class 'w6VYqd'
            parent_div = self.driver.find_element(By.CSS_SELECTOR, '.w6VYqd')
            # Within the parent, locating the scrollable div with the specified classes
            scrollable_div = parent_div.find_element(By.CSS_SELECTOR, '.m6QErb.DxyBCb.kA9KIf.dS8AEf')
            # Scrolling the element
            self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
            logging.debug("Successfully scrolled in scroll_reviews")
        except Exception as e:
            logging.debug(f"Error in scroll_reviews: {e}")

    def __get_logger(self):
        logging.debug(f"Starting __get_logger")
        logging.debug("Initializing logger...")
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

        logging.debug("Logger successfully initialized.")
        return logger

    def __get_driver(self, debug=False):
        logging.debug(f"Starting __get_driver")
        logging.debug("Initializing ChromeDriver...")
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
            options.add_argument("--window-size=1920,1080")

        options.add_argument("--disable-notifications")
        options.add_argument("--accept-lang=en-GB")
        
        # Configure the WebDriver to use the Tor SOCKS proxy
        options.add_argument("--proxy-server=socks5://127.0.0.1:9050")

        # Create a Service object with the ChromeDriver path
        service = Service(driver_path)

        # Create a ChromeDriver with the specified options and executable path
        input_driver = webdriver.Chrome(service=service, options=options)

        # click on google agree button so we can continue (not needed anymore)
        input_driver.get(GM_WEBPAGE)

        logging.debug("ChromeDriver successfully initialized.")
        return input_driver

    # cookies agreement click
    def __click_on_cookie_agreement(self):
        logging.debug(f"Starting __click_on_cookie_agreement")
        logging.debug("Clicking on cookie agreement...")
        try:
            agree = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "Reject all")]')))
            agree.click()

            # back to the main page
            # self.driver.switch_to_default_content()

            logging.debug("Successfully clicked on cookie agreement.")
            return True
        except:
            logging.debug("Failed to click on cookie agreement.")
            return False

    # util function to clean special characters
    def __filter_string(self, str):
        logging.debug(f"Starting __filter_string")
        logging.debug(f"Cleaning string")
        strOut = str.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
        logging.debug(f"Cleaned string: {strOut}")
        return strOut

