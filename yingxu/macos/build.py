"""Build a self-contained preview .app using only source and installed build dependencies."""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from macos_app import PREVIEW


def main():
    if sys.platform!='darwin' or platform.machine()!='arm64':
        raise SystemExit('Build on an Apple Silicon macOS host.')
    import imageio_ffmpeg
    work=ROOT/'.release-work/macos'
    work.mkdir(parents=True,exist_ok=True)
    media=work/'ffmpeg';shutil.copy2(imageio_ffmpeg.get_ffmpeg_exe(),media);media.chmod(0o755)
    output=work/'dist'
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir',
          '--name','YingXu','--osx-bundle-identifier','io.github.turnsolesama.yingxu.preview',
          '--distpath',str(output),'--workpath',str(work/'build'),'--specpath',str(work),
          '--paths',str(ROOT),'--hidden-import','macos_smoke','--hidden-import','macos_ui_smoke','--hidden-import','webview.platforms.cocoa',
          '--collect-data','webview','--copy-metadata','pywebview',
          '--add-data',str(ROOT/'frontend')+':frontend',
          '--add-binary',str(media)+':runtime/ffmpeg/bin',
          str(ROOT/'macos_app.py')]
    subprocess.run(args,cwd=ROOT,check=True)
    app=output/'YingXu.app'
    # Explicit deployment target and version shown by Finder.
    import plistlib
    info=app/'Contents/Info.plist'
    values=plistlib.loads(info.read_bytes())
    values.update(CFBundleShortVersionString='0.4.2',CFBundleVersion='40201',
                  LSMinimumSystemVersion='14.0',NSHighResolutionCapable=True,
                  NSDocumentsFolderUsageDescription='选择和管理您明确指定的视频创作项目与素材。')
    info.write_bytes(plistlib.dumps(values))
    subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True)
    subprocess.run(['codesign','--verify','--deep','--strict',str(app)],check=True)
    artifact=ROOT/'releases/macos-preview';artifact.mkdir(parents=True,exist_ok=True)
    staging=work/'delivery/YingXu';staging.mkdir(parents=True,exist_ok=True)
    shutil.copytree(app,staging/'YingXu.app',symlinks=True,dirs_exist_ok=True)
    shutil.copy2(ROOT/'macos/README.md',staging/'README-macOS.md')
    shutil.copy2(ROOT/'LICENSE',staging/'LICENSE')
    freeze=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True)
    (staging/'BUILD-DEPENDENCIES.txt').write_text(freeze,encoding='utf-8')
    # Record bundled third-party license metadata without importing user settings.
    import importlib.metadata as metadata
    licenses=staging/'licenses';licenses.mkdir(exist_ok=True)
    for distribution in metadata.distributions():
        name=distribution.metadata['Name']
        for file in distribution.files or []:
            if any(part.lower().startswith(('license','copying')) for part in file.parts):
                source=Path(distribution.locate_file(file))
                if source.is_file():
                    target=licenses/(name+'-'+str(file).replace('/','_'))
                    shutil.copy2(source,target)
    archive=artifact/f'YingXu-v{PREVIEW}-macOS-arm64.zip'
    subprocess.run(['ditto','-c','-k','--norsrc','--keepParent',str(staging),str(archive)],check=True)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (artifact/(archive.stem+'-SHA256.txt')).write_text(digest+'  '+archive.name+'\n')
    (artifact/(archive.stem+'-manifest.json')).write_text(json.dumps({
        'file':archive.name,'bytes':archive.stat().st_size,'sha256':digest,'version':PREVIEW,
        'platform':'macOS 14+','architecture':'arm64','signing':'ad-hoc; not notarized',
        'root':'YingXu/','contains_user_data':False},indent=2)+'\n')
    print(archive)


if __name__=='__main__':main()
