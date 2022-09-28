import hashlib
import os
import typing

from nornir_shared import prettyoutput


def FilesizeChecksum(filename) -> str:
    '''
       Returns the size of a file in bytes for use as a simple checksum
       
       :param str filename: path to file
       :return: Size of file as a string
       :rtype: str
       
    '''

    if os.path.exists(filename):
        Stats = os.stat(filename)
        return str(Stats.st_size)

    return ""


def DataChecksum(data: str | list | bytes | None) -> str:
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
            m.update(str(item).encode())
    elif isinstance(data, bytes):
        m.update(data)
    else:
        data = str(data).encode()
        m.update(data)

    return m.hexdigest()


def FileChecksum(filename: str) -> str | None:
    '''
    Return the md5 hash of a file read in txt mode
    
    :param str filename: path to file
    :return: md5 checksum
    :rtype str: 
    '''
    try:
        with open(filename) as f:
            data = f.read()
            f.close()
            dataStr = data.encode('utf-8')
            return DataChecksum(dataStr)

    except FileNotFoundError as fnfe:
        prettyoutput.LogErr("Could not compute checksum for non-existant file: " + filename + "\n")
        return None
    except Exception as e:
        prettyoutput.LogErr("Could not compute checksum for file: " + filename + "\n" + str(e))

    return None


if __name__ == '__main__':
    pass
