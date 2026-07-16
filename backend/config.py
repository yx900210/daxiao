import os
from dotenv import load_dotenv

load_dotenv()

DOUYIN_PROFILE_URL = os.getenv(
    "DOUYIN_PROFILE_URL",
    "https://www.douyin.com/user/MS4wLjABAAAAz-Nssy-G6nNshJODTK3VpEpjWsH1pMHODDPexGS5K-D6EAo5iASK_qCGRb7M5Rbe?from_tab_name=main",
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "daxiao.db")
VIDEOS_DIR = os.path.join(DATA_DIR, "videos")
SCREENSHOTS_DIR = os.path.join(DATA_DIR, "screenshots")

SCREENSHOT_INTERVAL = float(os.getenv("SCREENSHOT_INTERVAL", "2"))
BONSAI_FRAME_SECOND = float(os.getenv("BONSAI_FRAME_SECOND", "10"))
SUBTITLE_CROP_RATIO = (0.0, 0.70, 1.0, 1.0)
BONSAI_CROP_RATIO = (0.75, 0.0, 1.0, 1.0)
OCR_CONFIDENCE_MIN = float(os.getenv("OCR_CONFIDENCE_MIN", "0.7"))
DEDUP_SIMILARITY = float(os.getenv("DEDUP_SIMILARITY", "0.8"))
SCRAPE_DELAY_MIN = float(os.getenv("SCRAPE_DELAY_MIN", "2"))
SCRAPE_DELAY_MAX = float(os.getenv("SCRAPE_DELAY_MAX", "5"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
PAGE_SCROLL_COUNT = int(os.getenv("PAGE_SCROLL_COUNT", "5"))
CRON_SCHEDULE = os.getenv("CRON_SCHEDULE", "0 9 * * *")

CHROME_CDP_URL = os.getenv("CHROME_CDP_URL", "http://127.0.0.1:9222")
SCRAPE_TIMEOUT = int(os.getenv("SCRAPE_TIMEOUT", "60000"))

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://opencode.ai/zen/go/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
