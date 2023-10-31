from webdriver_manager.chrome import ChromeDriverManager

# Specify the ChromeDriver version you want to use
chrome_driver_version = "114.0.5735.90"

# Initialize the ChromeDriverManager with the specified version
driver_manager = ChromeDriverManager(version=chrome_driver_version)

# Get the path to the ChromeDriver executable
chrome_driver_path = driver_manager.install()