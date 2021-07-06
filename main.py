"""
This is a simple processing script that watches the shared drive and processes camera data
More complex verision (ui etc.) in slosh_rig repo
"""
import csv
import os
import shutil
import subprocess
import time

import imageio
import rawpy


def test_drive():  # 'X' (home wifi) or 'Y' (mobile hotspot)
    """
    Check which shared drive to use. 'X' (home wifi) or 'Y' (mobile hotspot) or 'W' (ethernet)
    :return: drive to use
    :raises WindowsError: if neither drive exists
    """
    if os.path.exists("W://"):
        dr = "W"
    elif os.path.exists("Y://"):
        dr = "Y"
    elif os.path.exists("X://"):
        dr = "X"
    else:
        raise WindowsError("No shared drive found!")
    return dr


class ProcessingWorker():
    """Worker that watches folder and processes RPi camera data"""

    def __init__(self, slowx, outname, fps):
        self.slowx = slowx
        self.outname = outname
        self.fps = fps
        self.drive = test_drive()

    def run(self):
        """Watch shared folder until frames appear, then start making video, finally tidy up"""
        tempdir = os.getcwd() + "\\temp"
        self.watch_and_clear(tempdir)
        self.move_and_convert_to_tiff(tempdir, self.drive)

        write_durations(tempdir, self.slowx)

        print("📽 Creating video...")
        create_video(tempdir, self.outname, self.slowx, self.fps)

        os.startfile(self.outname)
        self.tidy_up(tempdir)

    def watch_and_clear(self, temp_path):
        """Watches for files to appear in shared drive. Then clears out or creates temp folder."""
        print("🎞 Waiting for camera data...")

        while not os.path.exists(fr"{self.drive}:\tstamps.csv"):  # Wait for files to appear in shared folder
            time.sleep(1)

        print("📁 Transferring files and writing durations...")
        try:
            os.makedirs(temp_path)
        except WindowsError:  # if folder exists, clear it out
            for f in os.listdir(temp_path):
                os.remove(os.path.join(temp_path, f))

    def move_and_convert_to_tiff(self, temp_folder, drv):
        """
        Copy files to temp folder. Convert images from .raw to .tiff.
        :param temp_folder: self explanatory
        :param drv: shared drive to copy from
        """
        t1 = time.time()
        file_list = os.listdir(fr"{drv}:\\")
        file_total = len(file_list)
        for idx, filename in enumerate(file_list):
            if filename.endswith(".all") or filename.endswith(".csv"):
                fpath = fr"{drv}:\\{filename}"
                shutil.copy(fpath, temp_folder)
                if filename.endswith(".all"):
                    newpath = rf"{temp_folder}\\{filename}"
                    raw = rawpy.imread(newpath)
                    rgb = raw.postprocess()
                    imageio.imsave(f"{newpath[:-8]}.tiff", rgb)
        raw.close()  # the last file needs to be released, so that it can be deleted later
        t2 = time.time()
        print(f"Transfer took {t2 - t1:.2f} s")

    def tidy_up(self, temp_dir):
        """Clean up after yourself. Removes temp folder and all files within"""
        print("🗑️ Cleaning up...")

        shutil.rmtree(temp_dir)  # delete temp folder
        filelist = [f for f in os.listdir(fr"{self.drive}:/") if f is not f"{self.outname}.mp4"]
        lenfiles = len(filelist)
        for i, f in enumerate(filelist):  # clear out shared folder on pi
            os.remove(os.path.join(fr"{self.drive}:/", f))
        print("Finished")


def write_durations(temp_folder, slowdown):
    """Write a list of frame filenames and durations. Also prints video stats."""
    last_microsecond = 0
    dts = []
    with open(rf"{temp_folder}\\tstamps.csv") as csv_file, open(rf"{temp_folder}\\ffmpeg_concats.txt",
                                                                "w") as txt_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        for line_count, row in enumerate(csv_reader):
            current_microsecond = int(row[2])  # read timestamp
            if line_count > 0:
                dt = current_microsecond - last_microsecond
                dts.append(dt)
                txt_file.write(fr"file '{temp_folder}\out.{int(row[1]):06d}.tiff'")
                txt_file.write("\n")
                txt_file.write(f"duration {slowdown * dt / 1000000:08f}\n")
            last_microsecond = current_microsecond
        csv_file.close()
        txt_file.close()
    print_stats(dts, slowdown, line_count)


def print_stats(dts, slowx, line_count):
    avg_dt = (sum(dts) / len(dts)) / 1000000
    print("🎞")
    print(f" Average dt:   {avg_dt:.4f} s")
    print(f" Average fps:  {1 / avg_dt:.1f}")
    print(f" Output fps:   {(1 / avg_dt) / slowx:.1f}")
    print(f" Frames:       {line_count}")
    print(f" Video length: {line_count * avg_dt * slowx:.1f} s")


def create_video(frame_loc, output_name, slowdown, input_fps):
    """
    Sends command to ffmpeg to create a video from frames in a folder
    :param frame_loc: location of frames to compile
    :param output_name: filename to save as
    :param slowdown: how much slower the output will be
    :param input_fps: what fps the input was shot at
    :return:
    """
    min_fps = 25
    outfps = round(input_fps / slowdown)
    outfps = outfps if outfps < min_fps else min_fps
    # See 0375 Wiki for ffmpeg options explanation
    # IF SOMETHING IS WRONG WITH THIS NEXT LINE IT COULD BE CAUSE I CHANGED FROM x265 TO x264 TO FIX ENCODING PROBLEMS - JUST CHANGE x264 TO x265
    command = fr'ffmpeg -loglevel warning -r {outfps} -f concat -safe 0 -i {frame_loc}\ffmpeg_concats.txt -vcodec libx264 -x264-params log-level=-1:lossless=1 -b:v 1M -pix_fmt yuv420p -vf "pad=ceil(iw/2)*2:ceil(ih/2)*2" {output_name} -y'
    process = subprocess.run(command)


if __name__ == "__main__":
    slowx = 30
    fps = 440
    oname = "test_01.mp4"
    worker = ProcessingWorker(slowx, oname, fps)
    worker.run()
