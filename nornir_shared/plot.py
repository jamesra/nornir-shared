import matplotlib.pyplot as plt
import histogram
import argparse
from . import prettyoutput
from collections import Iterable
import numpy
from matplotlib.lines import fillStyles


def ProcessArgs():
    parser = argparse.ArgumentParser('AutoLevelHistogram')

    parser.add_argument('-MinCutoff',
                        action='store',
                        required=False,
                        default=None,
                        type=float,
                        help='What percentage of low intensity values are truncated',
                        dest='MinCutoffPercent'
                        )

    parser.add_argument('-MaxCutoff',
                        action='store',
                        required=False,
                        default=None,
                        type=float,
                        help='What percentage of high intensity values are truncated',
                        dest='MaxCutoffPercent'
                        )

    parser.add_argument('-line',
                        action='store',
                        required=False,
                        default=None,
                        type=float,
                        help='Place a line at the specified x location on the graph',
                        dest='LinePosition'
                        )

    parser.add_argument('-load',
                        action='store',
                        required=True,
                        help="The filename of the histogram.xml file to read",
                        dest='HistogramFilename')

    parser.add_argument('-save',
                        action='store',
                        required=False,
                        default=None,
                        help="Image filename to save",
                        dest='ImageFilename')

    args = parser.parse_args()
    return args


def Histogram(HistogramFilename, ImageFilename, MinCutoffPercent=None, MaxCutoffPercent=None, LinePosList=None, LineColorList=None, Title=None):
    Hist = histogram.Histogram.Load(HistogramFilename)

    if(Hist is None):
        prettyoutput.LogErr("PlotHistogram: Histogram file not found " + HistogramFilename)
        return

    if(Title is None):
        Title = 'Histogram of 16-bit intensity and cutoffs for 8-bit mapping'

    # prettyoutput.Log("Graphing histogram:")
    # prettyoutput.Log(str(Hist))

    ShowLine = False
    if(LinePosList is not None):
        ShowLine = True
        if not isinstance(LinePosList, list):
            LinePosList = [LinePosList]
    else:
        LinePosList = []

        # prettyoutput.Log( "Line Positions: " + str(LinePosList))

    ShowCutoffs = False
    if(MinCutoffPercent is not None or MaxCutoffPercent is not None):
        ShowCutoffs = True

    if(ShowCutoffs):
        # If the either number is greater than 1 assume it is an absolute value
        if(MinCutoffPercent >= 1 or MaxCutoffPercent >= 1):
            MinCutoff = MinCutoffPercent
            MinCutoffPercent = MinCutoff / Hist.MaxValue
            MaxCutoff = MaxCutoffPercent
            MaxCutoffPercent = 1 - (MaxCutoff / Hist.MaxValue)
        else:
            [MinCutoff, MaxCutoff] = Hist.AutoLevel(MinCutoffPercent, MaxCutoffPercent)

    BinValues = [(float(x) * float(Hist.BinWidth) + Hist.MinValue) for x in range(0, Hist.NumBins)]

    if(len(Hist.Bins) != Hist.NumBins):
        return

    if(ShowCutoffs):
        # prettyoutput.Log( "MinCutoff: " + str(float(MinCutoffPercent)*100) + '%')
        # prettyoutput.Log( "MaxCutoff: " + str((1 - float(MaxCutoffPercent))*100) + '%')
        pass

    # prettyoutput.Log( "Calculated Num Bin Values: " + str(len(BinValues)))
    # prettyoutput.Log( "Num Bin Values: " + str(len(Hist.Bins)))
    if(ShowCutoffs):
        print [MinCutoff, MaxCutoff]

    yMax = max(Hist.Bins)
 #  print 'Bins: ' + str(Hist.Bins)
 #  print 'Bin Sum: ' + str(sum(Hist.Bins))

    # print Hist.Bins
    plt.clf()
    plt.bar(BinValues, Hist.Bins, color='blue', edgecolor=None, linewidth=0, width=Hist.BinWidth)
    plt.title(Title)
    plt.ylabel('Counts')
    plt.xlabel('Intensity')
    #plt.xticks([])
    plt.yticks([])
    
    
    #For a time ticks were rendering very slowly, this turned out to be specific to numpy.linalg.inv on Python 2.7.6

    if(ShowCutoffs):
        if MinCutoff:
            plt.plot([MinCutoff, MinCutoff], [0, yMax], color='red')

            if MinCutoffPercent:
                plt.annotate(str(float(MinCutoffPercent) * 100) + '%', [MinCutoff, yMax * 0.5])

        if MaxCutoff:
            plt.plot([MaxCutoff, MaxCutoff], [0, yMax], color='red')

            if MaxCutoffPercent:
                plt.annotate(str((1 - float(MaxCutoffPercent)) * 100) + '%', [MaxCutoff, yMax * 0.5])


    if(ShowLine):
        color = 'green'
        if not LineColorList is None:
            if not isinstance(LineColorList,Iterable):
                color = LineColorList
                
        for i,linePos in enumerate(LinePosList):
            if isinstance(LineColorList, Iterable) and len(LinePosList) >= i:
                color = LineColorList[i]
                    
            plt.plot([linePos, linePos], [0, yMax], color=color)
            plt.annotate(str(linePos), [linePos, yMax * 0.9])
            
    
    minX = min(LinePosList + [Hist.MinValue])
    maxX = max(LinePosList + [Hist.MaxValue])
    plt.xlim([minX-Hist.BinWidth, maxX+Hist.BinWidth])

    if(ImageFilename is not None):
        #plt.show()
        plt.savefig(ImageFilename)
    else:
        plt.show()
        
    plt.close()


def Scatter(x, y, s=None, c=None, Title=None, XAxisLabel=None, YAxisLabel=None, OutputFilename=None, **kwargs):

    if s is None:
        s = 7
    # print Hist.Bins
    plt.cla()
    plt.scatter(x, y, s=s, c=c, marker='o', edgecolor=None, **kwargs)

    if not Title is None:
        plt.title(Title)
    if not YAxisLabel is None:
        plt.ylabel(YAxisLabel)
    if not XAxisLabel is None:
        plt.xlabel(XAxisLabel)

    plt.xlim(0, max(x) + 1)
    plt.ylim(0, max(y) + 1)

    if(OutputFilename is not None):
        plt.savefig(OutputFilename)
    else:
        plt.show()
        
    plt.close()


def PolyLine(PolyLineList, Title=None, XAxisLabel=None, YAxisLabel=None, OutputFilename=None):
    '''Poly line list is a list of lists of x,y points'''

    colors = ['black', 'blue', 'green', 'yellow', 'orange', 'red', 'purple']
    # print Hist.Bins
    plt.cla()
    for line in PolyLineList:
        numPoints = len(line[0])
        colorVal = 'black'
        if  numPoints < len(colors):
            colorVal = colors[numPoints]

        plt.plot(line[0], line[1], color=colorVal, alpha=0.5, marker='+', markerfacecolor='r', markeredgecolor='r', markersize=5)

    if not Title is None:
        plt.title(Title)
    if not YAxisLabel is None:
        plt.ylabel(YAxisLabel)
    if not XAxisLabel is None:
        plt.xlabel(XAxisLabel)

    if(OutputFilename is not None):
        plt.savefig(OutputFilename)
    else:
        plt.show()
        
    plt.close()
    

def VectorField(Points, Offsets, OutputFilename=None):
     
    
    plt.cla()
    plt.scatter(Points[:,1], Points[:,0], color='red', marker='s', alpha=0.5)
    
    assert(Points.shape[0] == Offsets.shape[0])
    for iRow in range(0,Points.shape[0]):
        Origin = Points[iRow,:]
        Offset = Offsets[iRow,:]
         
        Destination = Origin + Offset
         
        line = numpy.vstack((Origin, Destination))
        plt.plot(line[:,1], line[:,0], color='blue')
         
    if(OutputFilename is not None):
        plt.savefig(OutputFilename,dpi=300)
    else:
        plt.show()


if(__name__ == '__main__'):
    # Executed as a script, call the plothistogram function
    args = ProcessArgs()
    PlotHistogram(args.HistogramFilename, args.ImageFilename, args.MinCutoffPercent, args.MaxCutoffPercent, args.LinePosition)

    prettyoutput.Log(args)
