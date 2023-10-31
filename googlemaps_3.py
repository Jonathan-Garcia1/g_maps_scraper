
class GoogleMapsScraper:

    def __init__(self, debug=False):
        self.debug = debug
        self.driver = self.__get_driver()
        self.logger = self.__get_logger()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_value, tb)

        self.driver.close()
        self.driver.quit()

        return True

    def sort_by(self, url, ind):
        self.driver.get(url)
        self.__click_on_cookie_agreement()

        wait = WebDriverWait(self.driver, MAX_WAIT)

        # open dropdown menu
        clicked = False
        tries = 0
        while not clicked and tries < MAX_RETRY:
            try:
                menu_bt = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@data-value=\'Sort\']')))
                menu_bt.click()

                clicked = True
                time.sleep(3)
            except Exception as e:
                tries += 1
                self.logger.warn('Failed to click sorting button')

            # failed to open the dropdown
            if tries == MAX_RETRY:
                return -1

        # element of the list specified according to ind
        recent_rating_bt = self.driver.find_elements_by_xpath('//div[@role=\'menuitemradio\']')[ind]
        recent_rating_bt.click()

        # wait to load review (ajax call)
        time.sleep(5)

        return 0

    def get_places(self, keyword_list=None):
        df_places = pd.DataFrame()
        search_point_url_list = self._gen_search_points_from_square(keyword_list=keyword_list)

        for i, search_point_url in enumerate(search_point_url_list):
            print(search_point_url)

            if (i+1) % 10 == 0:
                print(f"{i}/{len(search_point_url_list)}")
                df_places = df_places[['search_point_url', 'href', 'name', 'rating', 'num_reviews', 'close_time', 'other']]
                df_places.to_csv('output/places_wax.csv', index=False)

            try:
                self.driver.get(search_point_url)
            except NoSuchElementException:
                self.driver.quit()
                self.driver = self.__get_driver()
                self.driver.get(search_point_url)

            # scroll to load all (20) places into the page
            scrollable_div = self.driver.find_element_by_css_selector(
                "div.m6QErb.DxyBCb.kA9KIf.dS8AEf.ecceSd > div[aria-label*='Results for']")
            for i in range(10):
                self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)

            # Get places names and href
            time.sleep(2)
            response = BeautifulSoup(self.driver.page_source, 'html.parser')
            div_places = response.select('div[jsaction] > a[href]')

            for div_place in div_places:
                place_info = {
                    'search_point_url': search_point_url.replace('https://www.google.com/maps/search/', ''),
                    'href': div_place['href'],
                    'name': div_place['aria-label']
                }

                df_places = df_places.append(place_info, ignore_index=True)

            # TODO: implement click to handle > 20 places

        df_places = df_places[['search_point_url', 'href', 'name']]
        df_places.to_csv('output/places_wax.csv', index=False)

    def get_reviews(self, offset):
        self.__scroll()

        # wait for other reviews to load (ajax)
        time.sleep(4)

        # expand review text
        self.__expand_reviews()

        # parse reviews
        response = BeautifulSoup(self.driver.page_source, 'html.parser')
        rblock = response.find_all('div', class_='jftiEf fontBodyMedium ')
        parsed_reviews = []
        for index, review in enumerate(rblock):
            if index >= offset:
                r = self.__parse(review)
                parsed_reviews.append(r)

                # logging to std out
                print(r)

        return parsed_reviews

    def get_account(self, url):
        self.driver.get(url)
        self.__click_on_cookie_agreement()

        # ajax call also for this section
        time.sleep(2)

        resp = BeautifulSoup(self.driver.page_source, 'html.parser')
        place_data = self.__parse_place(resp, url)

        return place_data

    def __parse(self, review):
        item = {}

        try:
            id_review = review['data-review-id']
        except Exception as e:
            id_review = None

        try:
            username = review['aria-label']
        except Exception as e:
            username = None

        try:
            review_text = self.__filter_string(review.find('span', class_='wiI7pd').text)
        except Exception as e:
            review_text = None

        try:
            rating = float(review.find('span', class_='kvMYJc')['aria-label'].split(' ')[0])
        except Exception as e:
            rating = None

        try:
            relative_date = review.find('span', class_='rsqaWe').text
        except Exception as e:
            relative_date = None

        try:
            n_reviews = review.find('div', class_='RfnDt').text.split(' ')[3]
        except Exception as e:
            n_reviews = 0

        try:
            user_url = review.find('button', class_='WEBjve')['data-href']
        except Exception as e:
            user_url = None

        item['id_review'] = id_review
        item['caption'] = review_text
        item['relative_date'] = relative_date
        item['retrieval_date'] = datetime.now()
        item['rating'] = rating
        item['username'] = username
        item['n_review_user'] = n_reviews
        item['url_user'] = user_url

        return item

    def __parse_place(self, response, url):
        place = {}

        try:
            place['name'] = response.find('h1', class_='DUwDvf lfPIob').text.strip()
        except Exception:
            place['name'] = None

        try:
            place['overall_rating'] = float(response.find('div', class_='F7nice').find('span', class_='ceNzKf')['aria-label'].split(' ')[0])
        except Exception:
            place['overall_rating'] = None

        try:
            place['n_reviews'] = int(response.find('div', class_='F7nice').text.split('(')[1].replace(',', '').replace(')', ''))
        except Exception:
            place['n_reviews'] = 0

        try:
            place['n_photos'] = int(response.find('div', class_='YkuOqf').text.replace('.', '').replace(',','').split(' ')[0])
        except Exception:
            place['n_photos'] = 0

        try:
            place['category'] = response.find('button', jsaction='pane.rating.category').text.strip()
        except Exception:
            place['category'] = None

        try:
            place['description'] = response.find('div', class_='PYvSYb').text.strip()
        except Exception:
            place['description'] = None

        b_list = response.find_all('div', class_='Io6YTe fontBodyMedium')
        try:
            place['address'] = b_list[0].text
        except Exception:
            place['address'] = None

        # Store the remaining details generically with error handling, as telephone, website vary in location and can not be reliably found using [n]
        for i in range(1, len(b_list)):
            try:
                place[f'detail_{i+1}'] = b_list[i].text
            except Exception:
                place[f'detail_{i+1}'] = None

        try:
            place['opening_hours'] = response.find('div', class_='t39EBf GUrTXd')['aria-label'].replace('\u202f', ' ')
        except:
            place['opening_hours'] = None

        place['url'] = url

        lat, long, z = url.split('/')[6].split(',')
        place['lat'] = lat[1:]
        place['long'] = long

        return place

    def _gen_search_points_from_square(self, keyword_list=None):
        keyword_list = [] if keyword_list is None else keyword_list

        square_points = pd.read_csv('input/square_points.csv')
        cities = square_points['city'].unique()

        search_urls = []

        for city in cities:
            df_aux = square_points[square_points['city'] == city]
            latitudes = df_aux['latitude'].unique()
            longitudes = df_aux['longitude'].unique()
            coordinates_list = list(itertools.product(latitudes, longitudes, keyword_list))

            search_urls += [f"https://www.google.com/maps/search/{coordinates[2]}/@{str(coordinates[1])},{str(coordinates[0])},{str(15)}z"
                            for coordinates in coordinates_list]

        return search_urls

    # Function to scroll the reviews
    def __scroll(self):
        try:
            scrollable_div = self.driver.find_element_by_css_selector('div.m6QErb.DxyBCb.kA9KIf.dS8AEf')
            self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
        except Exception as e:
            self.logger.warn("Error scrolling:", e)

    # Function to expand all reviews
    def __expand_reviews(self):
        try:
            links = self.driver.find_elements_by_css_selector('button.M77dve[aria-label^="More reviews"]')
            for l in links:
                l.click()
            time.sleep(2)  # Adjust sleep time if necessary
        except Exception as e:
            self.logger.warn("Error expanding reviews:", e)

    # Function to expand review text within a review block
    def __expand_review_text(self, review_block):
        try:
            more_button = review_block.find('button', class_='w8nwRe kyuRq')
            if more_button:
                data_review_id = more_button['data-review-id']
                more_button_selenium = self.driver.find_element_by_css_selector(f'button[data-review-id="{data_review_id}"].w8nwRe.kyuRq')
                if more_button_selenium:
                    more_button_selenium.click()
                    time.sleep(1)  # Adjust this delay as necessary to allow the text to expand
        except Exception as e:
            self.logger.warn(f"Error expanding review text: {e}")

    def __get_driver(self, debug=False):
        options = Options()

        if not self.debug:
            options.add_argument("--headless")
        else:
            options.add_argument("--window-size=1366,768")

        options.add_argument("--disable-notifications")
        options.add_argument("--accept-lang=en-GB")
        
        # Specify the path to the Chrome Beta binary
        chrome_binary_path = "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta"
        options.binary_location = chrome_binary_path
        
        # Specify the path to the downloaded ChromeDriver executable for Chrome Beta
        driver_path = "/Users/jongarcia/codeup-data-science/googlemaps-scraper/chromedriver-mac-x64 BETA/chromedriver"
        input_driver = webdriver.Chrome(executable_path=driver_path, options=options)
        input_driver.get(GM_WEBPAGE)

        return input_driver

    # cookies agreement click
    def __click_on_cookie_agreement(self):
        try:
            agree = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "Reject all")]')))
            agree.click()
            return True
        except:
            return False

    # util function to clean special characters
    def __filter_string(self, str):
        strOut = str.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
        return strOut

    # Function to get logger
    def __get_logger(self):
        logger = logging.getLogger('googlemaps-scraper')
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler('gm-scraper.log')
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        return logger


