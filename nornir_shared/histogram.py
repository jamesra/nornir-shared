import sys
import xml.dom.minidom
import string
import os
import prettyoutput
import copy
import math

class Histogram:

    def __init__(self):
        self.MinValue = sys.maxint
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

    @classmethod
    def Init(cls, minVal, maxVal, numBins=None, binVals=None):
        obj = Histogram()

        if numBins is None:
            # Add one for being zero based
            obj.NumBins = (maxVal + 1) - minVal
        else:
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
    def Load(cls, filename):
        obj = Histogram()

        if(os.path.exists(filename) == False):
            prettyoutput.Log("Mosaic file not found: " + filename)
            return

        xmlDoc = xml.dom.minidom.parse(filename)

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
        BinStrings = string.split(BinString)

        obj.Bins = list()

        for i in range(0, len(BinStrings)):
            obj.Bins.append(string.atoi(BinStrings[i]))

        if(len(obj.Bins) != obj.NumBins):
            prettyoutput.Log("ERROR: obj.Bins != obj.NumBins")
            prettyoutput.Log(str(obj))
            return

        return obj
       # prettyoutput.Log( self.Bins)

    @property
    def BinWidth(self):
        # Add one to MaxValue because 0 is a valid value
        return float((self.MaxValue + 1) - self.MinValue) / float(self.NumBins)


    def __FindValueAtPercentile(self, Bins, CutoffCount):

        Count = 0
        iCutoffBin = 0

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
        BaseValue = iCutoffBin * self.BinWidth

        ActualValue = BaseValue + (self.BinWidth * IntrabinPercentile)

        return ActualValue

    @property
    def Mean(self):
        MeanValue = self.__FindValueAtPercentile(self.Bins, (0.5 * float(self.NumSamples)))
        return MeanValue

    @property
    def Median(self):

        iBin = 0
        maxBin = 0
        iMax = 0

        for b in self.Bins:
            if maxBin < b:
                iMax = iBin
                maxBin = b

            iBin += 1

        return float(iMax) * self.BinWidth

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

        MinCutoffCount = None
        MaxCutoffCount = None

        iMaxBin = 0
        iMinBin = 0

        MinCutoffValue = self.MinValue
        MaxCutoffValue = self.MaxValue

        if not MinCutoff is None:
            assert(isinstance(MinCutoff, float))
            MinCutoffCount = float(MinCutoff) * float(self.NumSamples)
            MinCutoffValue = self.__FindValueAtPercentile(Bins=self.Bins, CutoffCount=MinCutoffCount)
            MinCutoffValue += self.MinValue

        if not MaxCutoff is None:
            assert(isinstance(MaxCutoff, float))
            MaxCutoffCount = float(MaxCutoff) * float(self.NumSamples)
            ReversedBins = copy.copy(self.Bins)
            ReversedBins.reverse()
            CutoffValue = self.__FindValueAtPercentile(Bins=ReversedBins, CutoffCount=MaxCutoffCount)
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

    def AddHistogram(self, bins):
        for i, count in enumerate(bins):
            self.Bins[i] = self.Bins[i] + count
            self.NumSamples = self.NumSamples + count

    def Add(self, values):
        '''Add a list of individual values to the histogram'''
        for val in values:
            iTargetBin = self.MapIntensityToBin(val)
            self.Bins[iTargetBin] = self.Bins[iTargetBin] + 1
            self.NumSamples = self.NumSamples + 1

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

    def Save(self, filename):

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
        with open(filename, 'w') as xmlFile:
            xmlFile.write(xmlStr)
            xmlFile.close()

