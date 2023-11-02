# -*- coding: utf-8 -*-
from googlemaps import GoogleMapsScraper
from datetime import datetime, timedelta
import argparse
import csv
from termcolor import colored
import time

import requests
from stem import Signal
from stem.control import Controller


ind = {'most_relevant' : 0 , 'newest' : 1, 'highest_rating' : 2, 'lowest_rating' : 3 }
HEADER = ['id', 'id_review', 'caption', 'relative_date', 'retrieval_date', 'rating', 'username', 'n_review_user', 'url_user', 'r_additional'] #'n_photo_user'
HEADER_W_SOURCE = ['id_review', 'caption', 'relative_date','retrieval_date', 'rating', 'username', 'n_review_user', 'url_user', 'r_additional', 'url_source'] #'n_photo_user'

def csv_writer(source_field, ind_sort_by, path='data/'):
    outfile= ind_sort_by + '_gm_reviews.csv'
    targetfile = open(path + outfile, mode='w', encoding='utf-8', newline='\n')
    writer = csv.writer(targetfile, quoting=csv.QUOTE_MINIMAL)

    if source_field:
        h = HEADER_W_SOURCE
    else:
        h = HEADER
    writer.writerow(h)

    return writer


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Google Maps reviews scraper.')
    parser.add_argument('--N', type=int, default=100, help='Number of reviews to scrape')
    parser.add_argument('--i', type=str, default='urls.txt', help='target URLs file')
    parser.add_argument('--sort_by', type=str, default='newest', help='most_relevant, newest, highest_rating or lowest_rating')
    parser.add_argument('--place', dest='place', action='store_true', help='Scrape place metadata')
    parser.add_argument('--debug', dest='debug', action='store_true', help='Run scraper using browser graphical interface')
    parser.add_argument('--source', dest='source', action='store_true', help='Add source url to CSV file (for multiple urls in a single file)')
    parser.set_defaults(place=False, debug=False, source=False)

    args = parser.parse_args()

    # store reviews in CSV file
    writer = csv_writer(args.source, args.sort_by)

with GoogleMapsScraper(debug=args.debug) as scraper:
    print("Scraper initialized successfully.")
    
    count = 0
    renew_interval = 10  # Renew IP every 10 places
    
    # Test Tor connection
    if not scraper.test_tor_connection():
        print("Exiting: Tor connection failed.")
        exit(1)
        
    with open(args.i, 'r') as urls_file:
        #This section starts the inclusion of ID
        reader = csv.DictReader(urls_file)
        for row in reader:
            url_id = row['id']
            url = row['url']
            # Ends the inclusion of ID

            # for url in urls_file:
            print(f"Processing URL: {url.strip()}")
            if args.place:
                account_info = scraper.get_account(url)
                print(f"Account Info: {account_info}")
            else:
                print("Attempting to sort reviews...")
                error = scraper.sort_by(url, ind[args.sort_by])
                print(f"Errors while readying to scrape: {error}")

                if error == 0:
                    n = 0
                    print(f"Starting to scrape reviews for {url.strip()}...")

                    while n < args.N:
                        print(colored(f'[Scraping from review {n}]', 'cyan'))
                        reviews = scraper.get_reviews(n)
                        print(f"Number of reviews fetched: {len(reviews)}")

                        if len(reviews) == 0:
                            print("No more reviews to fetch. Breaking out of the loop.")
                            break

                        for r in reviews:
                            ##This section starts the inclusion of ID
                            # row_data = list(r.values())
                            row_data = [url_id] + list(r.values())
                            # Ends inclusion of ID
                            if args.source:
                                row_data.append(url[:-1])
                            writer.writerow(row_data)
                            print(f"Review written to CSV")#: {row_data}")

                        n += len(reviews)
                else:
                    print(f"Error encountered when sorting reviews for URL: {url.strip()}")

            # Increment count and check if it's time to renew IP
            count += 1
            print(f'The current page count is {count}')
            if count % renew_interval == 0:
                print("Renewing Tor IP...")
                scraper.renew_tor_ip()
