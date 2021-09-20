import copy
from decimal import *
import math
import os
import sys
import xml.dom.minidom

import six

from nornir_shared import prettyoutput


def _FindValueAtPercentile(Bins, Percentile, BinWidth, BinMinValue):
        Count = 0
        iCutoffBin = 0

        NumValues = sum(Bins)
        CutoffCount = float(NumValues) * Percentile

        # OK, find the index where the cutoff occurs
        for i in range(0, len(Bins)):
            Count += Bins[i]
            iCutoffBin = i
            if Count > CutoffCount:
                break

        # OK, find where inside the bin the cutoff occurs
        StartingCount = Count - Bins[iCutoffBin]

        IntrabinPercentile = float(CutoffCount - StartingCount) / float(Bins[iCutoffBin])

        # Calculate the value
        BaseValue = iCutoffBin * BinWidth

        ActualValue = BaseValue + (BinWidth * IntrabinPercentile) + BinMinValue

        return ActualValue

class Histogram(object):

    def __init__(self):
        self.MinValue = float('NaN')
        self.MaxValue = 0
        self.NumBins = 0
        self.NumSamples = 0

        self.Bins = list()
        pass

    def __str__(self):
        s = 'Histogram\n'
        s += 'NumBins: ' + str(self.NumBins) + '\n'
        s += 'NumSamples: ' + str(self.NumSamples) + '\n'
        s += 'MinValue: ' + str(self.MinValue) + '\n'
        s += 'MaxValue: ' + str(self.MaxValue) + '\n'
 #       s += 'Bin Values: ' + str(self.Bins) + '\n'
        return s

    def __getstate__(self):
        save = {}
        save['MinValue'] = self.MinValue
        save['MaxValue'] = self.MaxValue
        save['NumBins'] = self.NumBins
        save['NumSamples'] = self.NumSamples
        save['Bins'] = self.Bins
        return save

    def __setstate__(self, state):
        self.__dict__.update(state)

    @classmethod
    def Init(cls, minVal, maxVal, numBins=None, binVals=None):
        obj = Histogram()

        

        if numBins is None:
            # Add one for being zero based
            obj.NumBins = (maxVal + 1) - minVal
            obj.NumBins = int(obj.NumBins)
        else:
            numBins = int(math.ceil(numBins))
            if not binVals is None:
                assert(len(binVals) == numBins)

            obj.NumBins = numBins

        obj.MinValue = minVal
        obj.MaxValue = maxVal

        if binVals is None:
            obj.Bins = [0] * obj.NumBins
            obj.NumSamples = 0
        else:
            obj.Bins = binVals
            obj.NumSamples = sum(binVals)
            obj.NumBins = len(binVals)

        return obj

    @classmethod
    def FromArray(cls, hist_array, minValue, binSize):
        obj = Histogram()

        obj.NumBins = len(hist_array)
        obj.Bins = list(hist_array)
        obj.MinValue = minValue 
        obj.MaxValue = (minValue + (binSize * obj.NumBins))-1
        obj.NumSamples = sum(hist_array)
        return obj

    @classmethod
    def FromXML(self, xml):
        obj = Histogram()

        if isinstance(xml, str):
            xmlDoc = xml.dom.minidom.parseString(xml)
        else:
            xmlDoc = xml
        #else:
            #raise InvalidOperation("xml parameter was not a string or XML minidom object")

        Elems = xmlDoc.getElementsByTagName('Histogram')
        if(len(Elems) != 1):
            prettyoutput.Log("Histogram tag not found in histogram XML")
            return

        HistogramElem = Elems[0]

        if(HistogramElem.hasAttribute('NumBins')):
            obj.NumBins = int(HistogramElem.getAttribute('NumBins'))

        if(HistogramElem.hasAttribute('NumSamples')):
            obj.NumSamples = int(HistogramElem.getAttribute('NumSamples'))

        if(HistogramElem.hasAttribute('MinValue')):
            obj.MinValue = float(HistogramElem.getAttribute('MinValue'))

        if(HistogramElem.hasAttribute('MaxValue')):
            obj.MaxValue = float(HistogramElem.getAttribute('MaxValue'))

        ChannelElems = HistogramElem.getElementsByTagName('Channel')

        if(len(ChannelElems) == 0):
            prettyoutput.Log("No channel element found in histogram")
            return

        ChannelElem = ChannelElems[0]

        BinNode = ChannelElem.firstChild
        BinString = BinNode.data

        BinStrings = BinString.split()

        obj.Bins = list()

        for i in range(0, len(BinStrings)):
            obj.Bins.append(int(BinStrings[i]))

        if(len(obj.Bins) != obj.NumBins):
            prettyoutput.Log("ERROR: obj.Bins != obj.NumBins")
            prettyoutput.Log(str(obj))
            return

        return obj

    @classmethod
    def Load(cls, filename): 
        if(os.path.exists(filename) == False):
            prettyoutput.Log("Mosaic file not found: " + filename)
            return

        return Histogram.FromXML(xml.dom.minidom.parse(filename))

    @property
    def BinWidth(self):
        # Add one to MaxValue because 0 is a valid value
        return float((self.MaxValue + 1) - self.MinValue) / float(self.NumBins)


    def _MinMaxBinIndicies(self, minVal=None, maxVal=None):
        '''Returns (iMin, iMax, MinBinValue) for a pair of minVal, maxVals'''

        AdjustedMin = self.MinValue

        iMin = 0
        if not minVal is None:
            iMin = self.MapIntensityToBin(minVal)
            AdjustedMin = minVal

        iMax = self.NumBins - 1
        if not maxVal is None:
            iMax = self.MapIntensityToBin(maxVal)

        return (iMin, iMax, AdjustedMin)

    def Median(self, minVal=None, maxVal=None):

        (iMin, iMax, AdjustedMin) = self._MinMaxBinIndicies(minVal, maxVal)

        MedianValue = _FindValueAtPercentile(self.Bins[iMin:iMax], 0.5, self.BinWidth, AdjustedMin)
        return MedianValue

    def BinValue(self, iBin, fraction=0.0):
        '''
        :param int iBin: Bin number
        :param float: Fraction within bin to return value for, defaults to minimum possible value
        :return: The value of the bin
        '''
        assert(fraction >= 0.0)
        assert(fraction <= 1.0)
        return (iBin * self.BinWidth) + (fraction * self.BinWidth) + self.MinValue
    
    def MinNonEmptyBin(self):
        '''
        :returns: The index of the lowest valued bin that contains a non-zero value, or None if all bins are empty
        '''
        #Remove empty buckets from the high-end of the histogram
        for i, count in enumerate(self.Bins):
            if count > 0:
                return i
        
        return None
        
    def MaxNonEmptyBin(self):
        '''
        :returns: The index of the highest valued bin that contains a non-zero value, or None if all bins are empty
        '''
        #Remove empty buckets from the high-end of the histogram
        for i in range(len(self.Bins)-2, -1, -1):
            if self.Bins[i] > 0:
                return i
        
        return None

    def Mean(self, minVal=None, maxVal=None):

        iBin = 0
        maxBin = 0
        _sum = Decimal()
        totalcount = Decimal()

        (iMin, iMax, AdjustedMin) = self._MinMaxBinIndicies(minVal, maxVal)

        for ibin in range(iMin, iMax):
            bincount = self.Bins[ibin]
            _sum += Decimal(bincount * self.BinValue(ibin, fraction=0.5))
            totalcount += bincount

        return float(_sum) / float(totalcount)

    def PeakValue(self, minVal=None, maxVal=None):

        maxBin = 0
        (iMin, iMax, AdjustedMin) = self._MinMaxBinIndicies(minVal, maxVal)

        PeakList = []

        for ibin in range(iMin, iMax):
            bincount = self.Bins[ibin]
            if maxBin < bincount:
                maxBin = bincount
                PeakList = [self.BinValue(ibin, fraction=0.5)]
            elif maxBin == bincount:
                PeakList.append(self.BinValue(ibin, fraction=0.5))
                
        if len(PeakList) == 0:
            return None

        return math.fsum(PeakList) / float(len(PeakList))

    def GammaAtValue(self, val, minVal=None, maxVal=None):
        '''Return the gamma value required to set target value to 0.5 in a leveled value'''
        if not isinstance(val, float):
            val = float(val)

        percentile = float(val) / float(self.MaxValue)
        if not (minVal is None and maxVal is None):
            percentile = (float(val) - float(minVal)) / (float(maxVal) - float(minVal))

        assert(percentile >= 0.0)
        Gamma = math.log(percentile) / math.log(0.5)
        return Gamma

    def AutoLevel(self, MinCutoff=None, MaxCutoff=None):
        '''Autolevel returns the value at the specified percentile.
           If none is passed either min or max value is returned
           If the percentile falls within the center of a bin we use a linear approximation to estimate the value'''

        # MinCutoffCount = None
        # MaxCutoffCount = None

        # iMaxBin = 0
        # iMinBin = 0

        MinCutoffValue = self.MinValue
        MaxCutoffValue = self.MaxValue

        if not MinCutoff is None:
            assert(isinstance(MinCutoff, float))
            # MinCutoffCount = float(MinCutoff) * float(self.NumSamples)
            MinCutoffValue = _FindValueAtPercentile(Bins=self.Bins, Percentile=MinCutoff, BinWidth=self.BinWidth, BinMinValue=self.MinValue)

        if not MaxCutoff is None:
            assert(isinstance(MaxCutoff, float))
            # MaxCutoffCount = float(MaxCutoff) * float(self.NumSamples)
            ReversedBins = list(copy.copy(self.Bins))
            ReversedBins.reverse()
            CutoffValue = _FindValueAtPercentile(Bins=ReversedBins, Percentile=MaxCutoff, BinWidth=self.BinWidth, BinMinValue=0)
            MaxCutoffValue = self.MaxValue - CutoffValue

#
#        if not MinCutoff is None:
#            MinCutoffCount = float(MinCutoff) * float(self.NumSamples)
#            Count = 0
#            for i in range(0, self.NumBins):
#                Count += self.Bins[i]
#                iMinBin = i
#                if(Count > MinCutoffCount):
#                    break
#
#            MinCutoffValue = self.(float(iMinBin) * self.BinWidth) + float(self.MinValue)
#
#        if not MaxCutoff is None:
#            MaxCutoffCount = float(MaxCutoff) * float(self.NumSamples)
#            Count = 0
#        #    prettyoutput.Log(range(self.NumBins - 1, 0,-1))
#            for i in range(self.NumBins - 1, 0,-1):
#                Count += self.Bins[i]
#                iMaxBin = i
#                if(Count > MaxCutoffCount):
#                    break
#
#            MaxCutoffValue = (float(iMaxBin) * self.BinWidth) + (self.BinWidth-1) + float(self.MinValue)

        # prettyoutput.Log("MinValue: " + str(self.MinValue) + " MaxValue: " + str(self.MaxValue) + " StepSize: " + str(self.BinWidth()))
        # prettyoutput.Log("iBins: " + str(iMinBin) + " " + str(iMaxBin))

        return [MinCutoffValue, MaxCutoffValue]

    def IncrementBin(self, intensity, count):
        '''Adds count to the bin that the intensity maps to'''
        iTargetBin = self.MapIntensityToBin(intensity)
        self.Bins[iTargetBin] = self.Bins[iTargetBin] + count
        self.NumSamples = self.NumSamples + count

    def AddHistogram(self, h):
        bins = None
        if isinstance(h, Histogram):
            assert(h.MinValue == self.MinValue)
            assert(h.BinWidth == self.BinWidth)
            assert(len(h.Bins) == len(self.Bins))
            bins = h.Bins
        else: #Otherwise assume an iterator
            assert(len(self.Bins) == len(h))
            bins = h
            
        for i, count in enumerate(bins):
            self.Bins[i] = self.Bins[i] + count
            self.NumSamples = self.NumSamples + count


    def __mapaddfunc(self, value):
        self.Bins[self.MapIntensityToBin(value)] += 1

    def Add(self, values):
        '''Add a list of individual values to the histogram'''

        for v in values:
            self.__mapaddfunc(v)

#         for val in values:
#             iTargetBin = self.MapIntensityToBin(val)
#             self.Bins[iTargetBin] = self.Bins[iTargetBin] + 1

        self.NumSamples += len(values)

        # prettyoutput.Log(str(self))

    def MapIntensityToBin(self, val):
        iBin = int(math.floor((val - self.MinValue) / self.BinWidth))

        if(iBin < 0):
            iBin = 0
        elif(iBin >= self.NumBins):
            iBin = self.NumBins - 1

        return iBin

    def BinsToString(self):

        binsString = ''
        for binVal in self.Bins:
            binsString = binsString + '\t' + str(int(binVal))

        return binsString
    
    @classmethod
    def Trim(cls, hObj):
        '''Remove leading and trailing empty buckets from the histogram'''
        
        hNew = cls.TryRemoveMaxValueOutlier(hObj, TrimOnly=True)
        if hNew is not None:
            hObj = hNew
            
        hNew = cls.TryRemoveMinValueOutlier(hObj, TrimOnly=True)
        if hNew is not None:
            hObj = hNew
        
        return hObj
    
    @staticmethod
    def TryRemoveMaxValueOutlier(hObj, TrimOnly=False):
        '''
        This functions checks the maximum value bucket of the histogram and the second to last histogram bucket.  If the 2nd to last is zero and the last is non-zero
        the last bucket is removed, all zeros from the last data value are removed, and a new histogram is returned.
        
        If the last bucket is zero then it is also removed  
        '''
        
        outlier_cutoff = math.ceil(hObj.NumSamples / 10000.0)
        if outlier_cutoff < 2:
            outlier_cutoff = 2
        HasOutlier = ((hObj.Bins[-1] > 0 and hObj.Bins[-1] < outlier_cutoff) and hObj.Bins[-2] == 0) and not TrimOnly
        Trimmable = hObj.Bins[-1] == 0
        
        if not HasOutlier and not Trimmable:
            return hObj
        
        
        while HasOutlier or Trimmable:
        
            #Remove empty buckets from the high-end of the histogram
            for i in range(len(hObj.Bins)-2, -1, -1):
                if hObj.Bins[i] > 0:
                    break
            
            #This means no values were above zero, lets just leave the histogram alone.  Probably never happens
            if i is None:
                return hObj
            
            newBins = hObj.Bins[0:i+1]
            
            hObj = Histogram.FromArray(newBins, hObj.MinValue, hObj.BinWidth)
            HasOutlier = ((hObj.Bins[-1] > 0 and hObj.Bins[-1] < outlier_cutoff) and hObj.Bins[-2] == 0) and not TrimOnly
            Trimmable = hObj.Bins[-1] == 0
            
    
        return hObj
    
    @staticmethod
    def TryRemoveMinValueOutlier(hObj, TrimOnly=False):
        '''
        This functions checks the minimum value bucket of the histogram and the second bucket.  If the 2nd is zero and the first is non-zero
        the first bucket is removed, all zero buckets beyond the first bucket are removed, and a new histogram is returned.
          
        If the first bucket is zero then it is also removed
        '''
        
        outlier_cutoff = math.ceil(hObj.NumSamples / 100000.0)
        if outlier_cutoff < 2:
            outlier_cutoff = 2
        HasOutlier = ((hObj.Bins[0] > 0 and hObj.Bins[0] < outlier_cutoff) and hObj.Bins[1] == 0) and not TrimOnly
        Trimmable = hObj.Bins[0] == 0
        
        if not HasOutlier and not Trimmable:
            return hObj
        
        while HasOutlier or Trimmable:
            
            #Remove empty buckets from the low-end of the histogram
            for i, count in enumerate(hObj.Bins):
                if i == 0:
                    continue #Skip the first bucket since we know we need to trim
                if count > 0:
                    break
            
            #This means no values were above zero, lets just leave the histogram alone.  Probably never happens
            if i is None:
                return hObj
            
            newBins = hObj.Bins[i:]
            
            hObj = Histogram.FromArray(newBins, hObj.BinValue(i), hObj.BinWidth)
            HasOutlier = ((hObj.Bins[0] > 0 and hObj.Bins[0] < outlier_cutoff) and hObj.Bins[1] == 0) and not TrimOnly
            Trimmable = hObj.Bins[0] == 0
    
        return hObj
        

    def ToXML(self):
        impl = xml.dom.minidom.getDOMImplementation()

        xmlDoc = impl.createDocument(None, 'Histogram', None)

        Elems = xmlDoc.getElementsByTagName('Histogram')
        if(len(Elems) != 1):
            return

        HistogramElem = Elems[0]

        HistogramElem.setAttribute('NumBins', str(int(self.NumBins)))
        HistogramElem.setAttribute('NumSamples', str(int(self.NumSamples)))
        HistogramElem.setAttribute('MinValue', str(self.MinValue))
        HistogramElem.setAttribute('MaxValue', str(self.MaxValue))

        ChannelElem = xmlDoc.createElement('Channel')
        binsString = self.BinsToString()
 #       prettyoutput.Log( binsString)
        channelText = xmlDoc.createTextNode(binsString)

        ChannelElem.appendChild(channelText)
        ChannelElem = HistogramElem.appendChild(ChannelElem)

        xmlStr = xmlDoc.toprettyxml()
        return xmlStr

    def Save(self, filename):
        xmlStr = self.ToXML()

        with open(filename, 'w') as xmlFile:
            xmlFile.write(xmlStr)
            xmlFile.close()

