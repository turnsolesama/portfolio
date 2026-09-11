from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from yingxu.jobs import Thumbnails,THUMBNAIL_FILTER
from yingxu.store import Store
from yingxu.runtime import ffmpeg_path


class ThumbnailTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='yingxu-thumbnails-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.store=Store(self.root/'data',self.root/'projects')

    def test_new_process_prunes_old_cache_without_generating_any_previews(self):
        cache=self.store.data_root/'thumbnails';cache.mkdir()
        for i in range(4):(cache/(f'{i:064x}'+'.jpg')).write_bytes(b'123')
        unknown=cache/'user.jpg';unknown.write_bytes(b'original')
        with patch('yingxu.jobs.CACHE_MAX_FILES',3),patch('yingxu.jobs.CACHE_TARGET_FILES',2):
            thumbs=Thumbnails(self.store);thumbs.pool.shutdown(wait=True)
        self.assertEqual(thumbs.generated,0)
        self.assertEqual(len(list(cache.glob('*.jpg'))),3)
        self.assertEqual(unknown.read_bytes(),b'original')

    def test_video_filter_bounds_both_axes_and_keeps_timeout_and_slots(self):
        thumbs=Thumbnails(self.store);thumbs.pool.shutdown(wait=True)
        key='a'*64;target=thumbs.root/(key+'.jpg');source=self.root/'synthetic.mp4';source.write_bytes(b'fake')
        def run(command,**kwargs):
            self.assertEqual(command[command.index('-vf')+1],THUMBNAIL_FILTER)
            self.assertIn('scale=640:640',THUMBNAIL_FILTER)
            self.assertIn('force_original_aspect_ratio=decrease',THUMBNAIL_FILTER)
            self.assertEqual(kwargs['timeout'],18)
            Path(command[-1]).write_bytes(b'preview')
        thumbs.ffmpeg='synthetic-ffmpeg';thumbs.slots.acquire();thumbs.pending.add(key)
        with patch('yingxu.jobs.subprocess.run',side_effect=run):thumbs._generate(key,source,'video',target)
        self.assertEqual(target.read_bytes(),b'preview');self.assertNotIn(key,thumbs.pending)
        self.assertEqual(source.read_bytes(),b'fake')

    def test_actual_ffmpeg_filter_for_portrait_landscape_and_square(self):
        ffmpeg=ffmpeg_path()
        if not ffmpeg:self.skipTest('FFmpeg not installed')
        try:from PIL import Image
        except ImportError:self.skipTest('Pillow not installed')
        for width,height in [(16,4096),(4096,16),(800,800)]:
            with self.subTest(width=width,height=height):
                output=self.root/f'{width}-{height}.jpg'
                subprocess.run([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-f','lavfi','-i',
                    f'color=c=black:s={width}x{height}', '-vf',THUMBNAIL_FILTER,'-frames:v','1','-threads','1','-y',str(output)],
                    stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True,timeout=10,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                with Image.open(output) as image:
                    self.assertGreater(image.width,0);self.assertGreater(image.height,0)
                    self.assertLessEqual(image.width,640);self.assertLessEqual(image.height,640)


if __name__=='__main__':unittest.main()
