# Copyright (C) 2026 M.Nesuka
# SPDX-License-Identifier: LGPL-2.1-or-later
# Dedicated third-party corresponding-source build recipe, not application code.
"""Controlled LGPL FFmpeg build; originals and all dependency sources are retained.

Requires the source archives and tool versions documented in BUILDING.md.
Only output/source trees below the supplied build directory are written.
"""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,tarfile

p=argparse.ArgumentParser()
p.add_argument('--compiler',type=Path,required=True)
p.add_argument('--make',type=Path,required=True)
p.add_argument('--pkgconf',type=Path,required=True)
p.add_argument('--shell',type=Path,required=True)
p.add_argument('--sources',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--jobs',type=int,default=2)
p.add_argument('--resume',action='store_true')
p.add_argument('--clean',action='store_true',help='Rebuild FFmpeg objects when compiler flags changed')
a=p.parse_args()
src=a.sources.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
prefix=out/'installed';prefix.mkdir(exist_ok=True)
env=os.environ.copy()
env['PATH']=os.pathsep.join(map(str,[a.compiler.resolve()/'bin',a.make.resolve().parent,a.pkgconf.resolve().parent,a.shell.resolve().parent,Path(sys.executable).parent]))+os.pathsep+env['PATH']
env['CC']='x86_64-w64-mingw32-clang';env['CXX']='x86_64-w64-mingw32-clang++'
env['PKG_CONFIG_PATH']=str(prefix/'lib/pkgconfig');env['PKG_CONFIG_LIBDIR']=str(prefix/'lib/pkgconfig')
env['SHELL']=a.shell.resolve().as_posix();env['MSYS2_PATH_TYPE']='inherit'
msys='/'+out.drive[0].lower()+out.as_posix()[2:]
file_maps=['-ffile-prefix-map='+out.as_posix()+'=third-party','-ffile-prefix-map='+msys+'=third-party']
# Environment flags avoid putting the private path into avcodec_configuration().
env['CFLAGS']=' '.join(file_maps)
def run(command,cwd=out):
 print(' '.join(map(str,command)),flush=True)
 subprocess.run(list(map(str,command)),cwd=cwd,env=env,check=True)
def extract(name):
 with tarfile.open(src/name) as t:t.extractall(out,filter='data')
if not a.resume:
 extract('zlib-1.3.1.tar.gz');extract('dav1d-1.5.1.tar.xz');extract('ffmpeg-7.1.5.tar.xz')
zlib=out/'zlib-1.3.1'
run([a.make.resolve(),'-f','win32/Makefile.gcc','-j'+str(a.jobs),'PREFIX=x86_64-w64-mingw32-','libz.a'],zlib)
(prefix/'lib').mkdir(exist_ok=True);(prefix/'include').mkdir(exist_ok=True)
for name in ('zlib.h','zconf.h'):shutil.copy2(zlib/name,prefix/'include'/name)
shutil.copy2(zlib/'libz.a',prefix/'lib/libz.a')
run([sys.executable,'-m','mesonbuild.mesonmain','setup',*(['--reconfigure'] if a.resume else []),out/'dav1d-build',out/'dav1d-1.5.1','--prefix='+prefix.as_posix(),'--libdir=lib','--buildtype=release','--default-library=static','-Dc_args='+','.join(file_maps),'-Denable_asm=false','-Denable_tools=false','-Denable_tests=false'])
run([sys.executable,'-m','mesonbuild.mesonmain','compile','-C',out/'dav1d-build','-j',a.jobs])
run([sys.executable,'-m','mesonbuild.mesonmain','install','-C',out/'dav1d-build'])
build=out/'ffmpeg-build';build.mkdir(exist_ok=True)
options=['--target-os=mingw32','--arch=x86_64','--cc=x86_64-w64-mingw32-clang','--cxx=x86_64-w64-mingw32-clang++',
 '--ar=x86_64-w64-mingw32-ar','--nm=x86_64-w64-mingw32-nm','--ranlib=x86_64-w64-mingw32-ranlib',
 '--pkg-config=pkgconf','--pkg-config-flags=--static','--prefix=/xag-poster',
 '--disable-autodetect','--disable-gpl','--disable-version3','--disable-nonfree','--disable-doc','--disable-debug',
 '--disable-ffplay','--disable-ffprobe','--disable-network','--disable-avdevice','--disable-x86asm',
 '--disable-encoders','--enable-encoder=png','--disable-muxers','--enable-muxer=image2',
 '--disable-filters','--enable-filter=scale,format,null','--disable-protocols','--enable-protocol=file,pipe',
 '--enable-static','--disable-shared','--enable-zlib','--enable-libdav1d',
 '--extra-cflags=-I../installed/include','--extra-ldflags=-L../installed/lib']
run([a.shell.resolve(),(out/'ffmpeg-7.1.5/configure').as_posix(),*options],build)
# Build-only change: a response file avoids Windows command-length limits.
library=out/'ffmpeg-7.1.5/ffbuild/library.mak'
before=library.read_text();old='\t$(AR) $(ARFLAGS) $(AR_O) $^'
after=before.replace(old,'\t$(file >$@.rsp,$^)\n\t$(AR) $(ARFLAGS) $(AR_O) @$@.rsp')
library.write_text(after,encoding='utf8')
import difflib
if before!=after:
 (out/'windows-response-files.patch').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/ffbuild/library.mak',tofile='b/ffbuild/library.mak')),encoding='utf8')
# Native Windows GNU Make needs drive paths, not MSYS /g/... paths.
for name in ('Makefile','ffbuild/config.mak'):
 path=build/name;path.write_text(path.read_text().replace(msys,out.as_posix()),encoding='utf8')
if a.clean:run([a.make.resolve(),'SHELL='+a.shell.resolve().as_posix(),'clean'],build)
run([a.make.resolve(),'-j'+str(a.jobs),'SHELL='+a.shell.resolve().as_posix(),'ffmpeg.exe'],build)
program=out/'ffmpeg.exe';shutil.copy2(build/'ffmpeg.exe',program)
result=subprocess.run([str(program),'-version'],capture_output=True,text=True,env=env,check=True)
(out/'build-configuration.txt').write_text(result.stdout+result.stderr,encoding='utf8')
(out/'build-options.json').write_text(json.dumps({'ffmpeg':'7.1.5','dav1d':'1.5.1','zlib':'1.3.1','options':options},indent=2),encoding='utf8')
print('Built',program,flush=True)
