# coding: utf-8
from __future__ import absolute_import
from __future__ import unicode_literals

import os
import errno
import operator
import posix
import stat
import time
import weakref
import itertools

import six
import fuse

from ... import errors
from ...enums import ResourceType, Seek
from ...opener import open_fs

from .error_tools import convert_fs_errors


class PyfilesystemFuseOperations(fuse.Operations):

    def __init__(self, filesystem):
        self.descriptors = {}
        self.fs = open_fs(filesystem)

    def __call__(self, op, *args):
        op_method = getattr(self, op, None)
        if op_method is None:
            raise fuse.FuseOSError(errno.ENOSYS)
        return op_method(*args)

    def _getfd(self):
        return next(x for x in itertools.count() if x not in self.descriptors)

    def access(self, path, amode):
        return 0

    bmap = None

    @convert_fs_errors
    def chmod(self, path, mode):
        raise fuse.FuseOSError(errno.EROFS)

    @convert_fs_errors
    def chown(self, path, uid, gid):
        raise fuse.FuseOSError(errno.EROFS)

    @convert_fs_errors
    def create(self, path, mode, fi=None):
        exclusive = (posix.O_EXCL & mode)
        if not self.fs.create(path) and exclusive:
            raise errors.FileExists(path)
        return self.open(path, mode)

    @convert_fs_errors
    def destroy(self, path):
        for handle in self.descriptors.values():
            handle.close()
        self.fs.close()

    @convert_fs_errors
    def flush(self, path, fd):
        self.descriptors[fd].flush()

    def fsync(self, path, datasync, fd):
        return 0

    def fsyncdir(self, path, datasync, fd):
        return 0

    # @convert_fs_errors
    def getattr(self, path, fh=None):

        try:
            info = self.fs.getinfo(path, ['details', 'access', 'stat', 'link'])

        except errors.ResourceNotFound:
            raise fuse.FuseOSError(errno.ENOENT)

        if info.has_namespace('stat'):
            return info.raw['stat']

        result = {}
        umask = os.umask(0)
        os.umask(umask)

        if info.has_namespace('details'):
        # FIXME: some namespaces could be unavailable
            result['st_atime'] = int(info.accessed.timestamp())
            result['st_mtime'] = int(info.modified.timestamp())
            result['st_ctime'] = int((info.created or info.metadata_changed).timestamp())
            result['st_size'] = info.size

        if info.has_namespace('access'):
            result['st_uid'] = info.uid
            result['st_gid'] = info.gid

        # TODO: support links ?
        # if info.is_link:
        #     result['st_mode'] = stat.S_IFLNK
        if info.type is ResourceType.directory:
            result['st_mode'] = stat.S_IFDIR
        else:
            result['st_mode'] = stat.S_IFREG

        if info.has_namespace('access') and info.permissions is not None:
            result['st_mode'] |= info.permissions.mode
        elif info.type is ResourceType.directory:
            result['st_mode'] |= 0o777 & ~umask
        else:
            result['st_mode'] |= 0o666 & ~umask

        if path == '/':
            result['st_nlink'] = 2

        return result

    @convert_fs_errors
    def getxattr(self, path, name, position=0):
        raise fuse.FuseOSError(errno.ENOTSUP)

    @convert_fs_errors
    def init(self, path):
        pass

    def listxattr(self, path):
        return []

    @convert_fs_errors
    def mkdir(self, path, mode):
        self.fs.makedir(path)

    @convert_fs_errors
    def open(self, path, flags):
        # FIXME: mode should be determined from file ?
        mode = 'r+'
        fd = self._getfd()
        self.descriptors[fd] = self.fs.openbin(path, mode)
        return fd

    @convert_fs_errors
    def read(self, path, size, offset, fd):
        print(path, size, offset, fd)
        handle = self.descriptors[fd]
        handle.seek(offset, Seek.set)
        return handle.read(size)

    @convert_fs_errors
    def readdir(self, path, fh):
        return ['.', '..'] + self.fs.listdir(path)

    @convert_fs_errors
    def readlink(self, path):
        raise fuse.FuseOSError(errno.ENOENT)

    @convert_fs_errors
    def release(self, path, fh):
        self.descriptors[fh].close()

    @convert_fs_errors
    def removexattr(self, path, name):
        raise fuse.FuseOSError(errno.ENOTSUP)

    @convert_fs_errors
    def rename(self, old, new):
        if self.fs.gettype(old) is ResourceType.directory:
            self.fs.movedir(old, new)
        else:
            self.fs.move(old, new)

    @convert_fs_errors
    def rmdir(self, path):
        self.fs.removedir(path)

    def setxattr(self, path, name, value, options, position=0):
        raise fuse.FuseOSError(errno.ENOTSUP)

    def statfs(self, path):
        return {}

    def symlink(self, target, source):
        raise fuse.FuseOSError(errno.EROFS)

    @convert_fs_errors
    def truncate(self, path, length, fd=None):
        if fd is None:
            fd = self.open(path, stat.S_IWRITE)
        self.descriptors[fd].truncate(length)

    @convert_fs_errors
    def unlink(self, path):
        self.fs.remove(path)

    @convert_fs_errors
    def utimens(self, path, times=None):
        now = time.time()
        atime, mtime = (times[0], times[1]) if times else (now, now)
        info = {'details': {"accessed": atime, "modified": mtime}}
        self.fs.setinfo(path, info)

    @convert_fs_errors
    def write(self, path, data, offset, fd):
        fh = self.descriptors[fd]
        fh.seek(offset, Seek.set)
        return fh.write(data)