import os
import ee
from dotenv import load_dotenv

load_dotenv()
ee.Initialize(project=os.getenv("EE_PROJECT"))
pt = ee.Geometry.Point([77.21, 28.61])
elev = ee.Image("USGS/SRTMGL1_003").sample(pt, 30).first().getInfo()
print("Earth Engine works. Elevation at central Delhi:", elev["properties"])