import argparse
import os
import shutil
import time
from functools import partial

import requests
import tqdm


def download(url, path, fname, redownload=False):
    """
    Downloads file using `requests`. If ``redownload`` is set to false, then
    will not download tar file again if it is present (default ``True``).

    :param url: string of base url to download from
    :param path: string of base directory to save
    :param fname: destination filename
    :param redownload: checks if file already exists, defaults to False
    :raises RuntimeWarning: Interrupted Network Connection
    :raises RuntimeWarning: wrong download payload size
    """
    outfile = os.path.join(path, fname)
    download = not os.path.isfile(outfile) or redownload
    print("[ downloading: " + url + " to " + outfile + " ]")
    retry = 5
    exp_backoff = [2 ** r for r in reversed(range(retry))]

    pbar = tqdm.tqdm(unit="B", unit_scale=True, desc="Downloading {}".format(fname))

    while download and retry >= 0:
        resume_file = outfile + ".part"
        resume = os.path.isfile(resume_file)
        if resume:
            resume_pos = os.path.getsize(resume_file)
            mode = "ab"
        else:
            resume_pos = 0
            mode = "wb"
        response = None

        with requests.Session() as session:
            try:
                header = (
                    {
                        "Range": "bytes=%d-" % resume_pos,
                        "Accept-Encoding": "identity",
                    }
                    if resume
                    else {}
                )
                response = session.get(url, stream=True, timeout=5, headers=header)

                # negative reply could be 'none' or just missing
                if resume and response.headers.get("Accept-Ranges", "none") == "none":
                    resume_pos = 0
                    mode = "wb"

                CHUNK_SIZE = 32768
                total_size = int(response.headers.get("Content-Length", -1))
                # server returns remaining size if resuming, so adjust total
                total_size += resume_pos
                pbar.total = total_size
                done = resume_pos

                with open(resume_file, mode) as f:
                    for chunk in response.iter_content(CHUNK_SIZE):
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
                        if total_size > 0:
                            done += len(chunk)
                            if total_size < done:
                                # don't freak out if content-length was too small
                                total_size = done
                                pbar.total = total_size
                            pbar.update(len(chunk))
                    break
            except requests.exceptions.ConnectionError:
                retry -= 1
                pbar.clear()
                if retry >= 0:
                    print("Connection error, retrying. (%d retries left)" % retry)
                    time.sleep(exp_backoff[retry])
                else:
                    print("Retried too many times, stopped retrying.")
            finally:
                if response:
                    response.close()
    if retry < 0:
        raise RuntimeWarning("Connection broken too many times. Stopped retrying.")

    if download and retry > 0:
        pbar.update(done - pbar.n)
        if done < total_size:
            raise RuntimeWarning(
                "Received less data than specified in "
                + "Content-Length header for "
                + url
                + "."
                + " There may be a download problem."
            )
        move(resume_file, outfile)

    pbar.close()


def _get_confirm_token(response):
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            return value
    return None


def download_from_google_drive(gd_id, destination):
    """Uses the requests package to download a file from Google Drive.

    :param gd_id: google drive id
    :param destination: file destination to save to
    """
    URL = "https://docs.google.com/uc?export=download"

    with requests.Session() as session:
        response = session.get(URL, params={"id": gd_id}, stream=True)
        token = _get_confirm_token(response)

        if token:
            response.close()
            params = {"id": gd_id, "confirm": token}
            response = session.get(URL, params=params, stream=True)

        CHUNK_SIZE = 32768
        with open(destination, "wb") as f:
            for chunk in tqdm.tqdm(
                response.iter_content(CHUNK_SIZE), desc="Downloading"
            ):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
        response.close()


move = shutil.move


def untar(path, fname, deleteTar=True):
    """
    Unpacks the given archive file to the same directory, then (by default)
    deletes the archive file.

    :param path: string path of base directory
    :param fname: string of filename to untar from file
    :param deleteTar: delete tar after extraction, defaults to True
    """
    print("unpacking " + fname)
    fullpath = os.path.join(path, fname)
    shutil.unpack_archive(fullpath, path)
    if deleteTar:
        os.remove(fullpath)


make_dir = partial(os.makedirs, exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", type=str)
    parser.add_argument("path", type=str)
    parser.add_argument("fname", type=str)

    args = parser.parse_args()

    make_dir(args.path)
    if "drive.google.com" in args.url:
        download_from_google_drive(
            args.url[args.url.index("id=") + 3 :],
            os.path.join(args.path, args.fname),
        )
    else:
        download(args.url, args.path, args.fname)
    if "tar.gz" in args.fname:
        untar(args.path, args.fname)


if __name__ == "__main__":
    main()
