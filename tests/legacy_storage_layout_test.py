#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import argparse
import subprocess,tempfile

parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'FsCrypt.cpp')
p=parser.parse_args().source
s=p.read_text()
helpers=s[s.index('static bool preserve_existing_legacy_layout()'):s.index('static bool prepare_special_dirs()')]
start=s.index('bool fscrypt_prepare_user_storage(')
prefix=s[start:s.index('    // Internal storage must be prepared',start)]
special=s[s.index('static bool prepare_special_dirs()'):s.index('    // Ensure that /data/data',s.index('static bool prepare_special_dirs()'))]
fixture=r'''
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>
using userid_t=unsigned;
static bool enabled=false;
static int modern_prepares=0;
static std::string data_root,data_data_dir,data_user_0_dir;
#define DATA_MNT_POINT data_root
#define LOG(x) std::cerr
namespace android::os { struct IVold { enum {STORAGE_FLAG_DE=1,STORAGE_FLAG_CE=2}; }; }
namespace android::base {
bool GetBoolProperty(const char*,bool) { return enabled; }
bool Readlink(const std::string& path,std::string* result) {
    char value[4096]; auto count=readlink(path.c_str(),value,sizeof(value));
    if(count<0) return false; result->assign(value,count); return true;
}
}
static std::string escape_empty(const std::string& s) { return s; }
'''+helpers+prefix+'    ++modern_prepares; return true;\n}\n'+special+'    ++modern_prepares; return true;\n}\n'+r'''
int main() {
    namespace fs=std::filesystem;
    char folder[]="/tmp/legacy-layout-test-XXXXXX";
    assert(mkdtemp(folder));
    data_root=folder; data_data_dir=data_root+"/data"; data_user_0_dir=data_root+"/user/0";
    for(const auto* name:{"data","user","user_de/0","system_de/0","misc_de/0","system_ce/0","misc_ce/0","media/0"})
        fs::create_directories(data_root+"/"+name);
    fs::create_symlink(data_data_dir,data_user_0_dir);
    auto sentinel=data_data_dir+"/keep";
    std::ofstream(sentinel)<<"unchanged";
    struct stat before,after; assert(lstat(sentinel.c_str(),&before)==0);
    assert(fscrypt_prepare_user_storage("",0,3));
    assert(prepare_special_dirs()); assert(modern_prepares==2);
    enabled=true;
    for(int flags:{0,1,2,3}) assert(fscrypt_prepare_user_storage("",0,flags));
    assert(prepare_special_dirs()); assert(modern_prepares==2);
    assert(!fscrypt_prepare_user_storage("adoptable",0,3));
    assert(!fscrypt_prepare_user_storage("",10,3));
    fs::remove(data_root+"/user_de/0");
    assert(!fscrypt_prepare_user_storage("",0,1));
    assert(!fs::exists(data_root+"/user_de/0"));
    assert(fscrypt_prepare_user_storage("",0,2));
    fs::create_directories(data_root+"/user_de/0");
    fs::remove(data_user_0_dir); fs::create_directory(data_user_0_dir);
    assert(!prepare_special_dirs()); assert(fs::is_directory(data_user_0_dir));
    assert(!fscrypt_prepare_user_storage("",0,3));
    fs::remove(data_user_0_dir); fs::create_symlink(data_root+"/media/0",data_user_0_dir);
    assert(!prepare_special_dirs()); assert(fs::is_symlink(data_user_0_dir));
    assert(modern_prepares==2);
    fs::remove(data_user_0_dir); fs::create_directory(data_user_0_dir);
    enabled=false;
    assert(prepare_special_dirs());
    assert(fscrypt_prepare_user_storage("",0,3));
    assert(modern_prepares==4);
    assert(lstat(sentinel.c_str(),&after)==0);
    assert(before.st_ino==after.st_ino && before.st_mode==after.st_mode && before.st_size==after.st_size);
    std::string content; std::ifstream(sentinel)>>content; assert(content=="unchanged");
    fs::remove_all(data_root);
    std::cout<<"Legacy layout validation preserves existing files and aliases; default setup is unchanged.\n";
}
'''
with tempfile.TemporaryDirectory() as folder:
    path=Path(folder)/'test.cpp'; path.write_text(fixture)
    out=Path(folder)/'test'
    subprocess.run(['g++','-std=c++17','-O1','-g','-fsanitize=address,undefined',str(path),'-o',str(out)],check=True)
    subprocess.run([str(out)],check=True)
