
class FilesOpener(object):
    def __init__(self, paths, key_format='file{}'):
        if not isinstance(paths, list):
            paths = [paths]

        self.paths = paths
        self.key_format = key_format
        self.opened_files = []

    def __enter__(self):
        return self.open_files()

    def __exit__(self, type, value, traceback):
        self.close_files()

    def open_files(self):
        self.close_files()

        files = []

        for x, file in enumerate(self.paths):
            if hasattr(file, 'read'):
                f = file

                if hasattr(file, 'name'):
                    filename = file.name
                else:
                    filename = '.jpg'
            else:
                filename = file
                f = open(filename, 'rb')
                self.opened_files.append(f)

            ext = filename.split('.')[-1]
            files.append(
                (self.key_format.format(x), ('file{}.{}'.format(x, ext), f))
            )

        return files

    def close_files(self):
        for f in self.opened_files:
            f.close()

        self.opened_files.clear()
