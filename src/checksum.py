'''
Created on Jul 11, 2012

@author: Jamesan
'''
import prettyoutput;
import os
import hashlib

def FilesizeChecksum(filename):
    if os.path.exists(filename):
        Stats = os.stat(filename);
        return str(Stats.st_size);

    return "";

def DataChecksum(data):
    '''Removes whitespace from strings before calculating hash'''
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
    '''Return the md5 hash of a file read in txt mode'''
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