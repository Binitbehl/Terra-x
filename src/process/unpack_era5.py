import glob, os, shutil, zipfile

for f in glob.glob("data/raw/era5/*"):
    if os.path.isdir(f):
        continue
    name = os.path.splitext(os.path.basename(f))[0]
    if zipfile.is_zipfile(f):
        with zipfile.ZipFile(f) as z:
            z.extractall(f"data/raw/era5/{name}")
        os.remove(f)
        print("unzipped", f)
    elif not f.endswith(".nc"):
        shutil.move(f, f + ".nc")
        print("renamed", f)