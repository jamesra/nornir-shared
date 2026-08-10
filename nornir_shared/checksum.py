import hashlib
import os

from nornir_shared import prettyoutput


def FilesizeChecksum(filename) -> str | None:
    '''
       Returns the size of a file in bytes for use as a simple checksum
       
       :param str filename: path to file
       :return: Size of file as a string
       :rtype: str
       :raises FileNotFoundError: If the file does not exist
       
    '''

    stats = os.stat(filename)
    return str(stats.st_size) 


def DataChecksum(data: str | list | bytes | None) -> str | None:
    '''
     Removes whitespace from strings before calculating md5 checksum
    :param obj data: string, list or object convertible to string
    :return: md5 checksum
    :rtype str:
    '''

    if data is None:
        return None

    m = hashlib.md5()

    if isinstance(data, str):
        data = "".join(data.split())
        m.update(data.encode())
    elif isinstance(data, list):
        for item in data:
            # Length-prefix each item so ["ab","c"] and ["a","bc"] do not collide.
            encoded = str(item).encode()
            m.update(len(encoded).to_bytes(4, byteorder='big', signed=False))
            m.update(encoded)
    elif isinstance(data, bytes):
        m.update(data)
    else:
        data = str(data).encode()
        m.update(data)

    return m.hexdigest()


def FileChecksum(filename: str) -> str | None:
    '''
    Return the md5 hash of a file's raw bytes.

    :param str filename: path to file
    :return: md5 checksum
    :rtype str:
    :raises FileNotFoundError: If the file does not exist
    '''
    try:
        with open(filename, 'rb') as f:
            return DataChecksum(f.read())

    except FileNotFoundError:
        prettyoutput.LogErr("Could not compute checksum for non-existant file: " + filename + "\n")
        raise
    except Exception as e:
        prettyoutput.LogErr("Could not compute checksum for file: " + filename + "\n" + str(e))
        raise

    return None


if __name__ == '__main__':
    pass
