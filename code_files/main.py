import os
import time
salt = int(time.time())
artifacts_dir = f"ml-artifacts-{salt}"
coll = [4,6,7,2,3,9,4,2,18,21,72,76,23,24]

def create_dir(path: str):
    try:
        mod_path = path.split("/")
        mod_path.pop(0)
        root_dir, artifacts, file = mod_path
        os.chdir("/" + root_dir + "/")
        os.mkdir(artifacts)
    except FileExistsError:
        pass

def save(path: str, data: str, flag: bool=False):
    if not flag:
        create_dir(path)
    with open(path, "w+") as file:
        file.write(data)


def load(path: str):
    with open(path, "r+") as file:
        data = file.read()
    return data


def pre_processing():
    data = list(map(lambda x: x ** 2, coll))
    save(path=f"/tmp/{artifacts_dir}/processed_data.txt", data=str(data))


def train():
    data = load(f"/tmp/{artifacts_dir}/processed_data.txt")
    save(path=f"/tmp/{artifacts_dir}/model.pkl", data=str(data))


def test():
    data = "Test completed successfully"
    save(path=f"/tmp/{artifacts_dir}/testfile.txt", data=str(data))


def start_pipeline():
    pre_processing()
    train()
    test()


if __name__ == "__main__":
    save(path="/tmp/artifacts.salt", data=str(salt), flag=True)
    start_pipeline()