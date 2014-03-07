
from . import prettyoutput;
import os
import hashlib

def FilesizeChecksum(filename):
    '''
       Returns the size of a file in bytes for use as a simple checksum
       
       :param str filename: path to file
       :return: Size of file as a string
       :rtype: str
       
    '''

    if os.path.exists(filename):
        Stats = os.stat(filename);
        return str(Stats.st_size);

    return "";

def DataChecksum(data):
    '''
    Removes whitespace from strings before calculating md5 checksum
    
    :param obj data: string, list or object convertible to string
    :return: md5 checksum
    :rtype str:
    '''

    if data is None:
        return None;

    m = hashlib.md5()

    if(isinstance(data, str)):
        data = "".join(data.split());
        m.update(data)
    elif(isinstance(data, list)):
        for item in data:
            m.update(str(item));
    else:
        data = str(data)
        m.update(data)

    return m.hexdigest()

def FileChecksum(filename):
    '''
    Return the md5 hash of a file read in txt mode
    
    :param str filename: path to file
    :return: md5 checksum
    :rtype str: 
    '''
    if not os.path.exists(filename):
        prettyoutput.LogErr("Could not compute checksum for non-existant file: " + filename + "\n");
        return None;

    try:

        with open(filename) as f:
            data = f.read();
            f.close();
            dataStr = data.encode('utf-8');
            return DataChecksum(dataStr);

    except Exception as e:
        prettyoutput.LogErr("Could not compute checksum for file: " + filename + "\n" + str(e));

    return None

if __name__ == '__main__':
    pass