import argparse
from collections.abc import Iterable
import matplotlib.pyplot as plt
from matplotlib.lines import fillStyles
import numpy
from numpy.typing import NDArray
from nornir_shared import histogram
from nornir_shared import prettyoutput
from enum import Enum
import nornir_imageregistration

plt.ioff()

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

def SetSquareAspectRatio(ax): 
    #set aspect ratio to 1
    ratio = 1.0
    x_left, x_right = plt.xlim()
    y_low, y_high = plt.ylim()
    ax.set_aspect(abs((x_right-x_left)/(y_low-y_high))*ratio)
    return

def Histogram(HistogramOrFilename, ImageFilename=None, MinCutoffPercent=None,
              MaxCutoffPercent=None, LinePosList=None, LineColorList=None,
              Title: str | None =None, 
              xlabel: str | None =None, ylabel: str | None = None,
              minX:float | None = None, maxX:float | None = None, dpi: int | None = None,
              range_is_power_of_two: bool = False):
    Hist = None

    if dpi is None:
        dpi = 150
    
    if ImageFilename is not None:
        # plt.show()
        plt.ioff()
    
    if isinstance(HistogramOrFilename, histogram.Histogram):
        Hist = HistogramOrFilename
    else:
        Hist = histogram.Histogram.Load(HistogramOrFilename)

        if Hist is None:
            prettyoutput.LogErr("PlotHistogram: Histogram file not found " + HistogramOrFilename)
            return

    if Title is None:
        Title = 'Histogram of 16-bit intensity and cutoffs for 8-bit mapping'
        
    if xlabel is None:
        xlabel = 'Intensity'
        
    if ylabel is None:
        ylabel = 'Counts'

    # prettyoutput.Log("Graphing histogram:")
    # prettyoutput.Log(str(Hist))

    ShowLine = False
    if LinePosList is not None:
        ShowLine = True
        if not isinstance(LinePosList, list):
            LinePosList = [LinePosList]
    else:
        LinePosList = []

        # prettyoutput.Log( "Line Positions: " + str(LinePosList))

    ShowCutoffs = False
    if MinCutoffPercent is not None or MaxCutoffPercent is not None:
        ShowCutoffs = True

    if ShowCutoffs:
        # If the either number is greater than 1 assume it is an absolute value
        if MinCutoffPercent >= 1 or MaxCutoffPercent > 1:
            MinCutoff = MinCutoffPercent
            MinCutoffPercent = MinCutoff / Hist.MaxValue
            MaxCutoff = MaxCutoffPercent
            MaxCutoffPercent = 1 - (MaxCutoff / Hist.MaxValue)
        else:
            [MinCutoff, MaxCutoff] = Hist.AutoLevel(MinCutoffPercent, MaxCutoffPercent)

    BinValues = [(float(x) * float(Hist.BinWidth) + Hist.MinValue) for x in range(0, Hist.NumBins)]

    if len(Hist.Bins) != Hist.NumBins:
        return

    if ShowCutoffs:
        # prettyoutput.Log( "MinCutoff: " + str(float(MinCutoffPercent)*100) + '%')
        # prettyoutput.Log( "MaxCutoff: " + str((1 - float(MaxCutoffPercent))*100) + '%')
        pass

    # prettyoutput.Log( "Calculated Num Bin Values: " + str(len(BinValues)))
    # prettyoutput.Log( "Num Bin Values: " + str(len(Hist.Bins)))
    if ShowCutoffs:
        prettyoutput.Log(f'Histogram cutoffs: {MinCutoff},{MaxCutoff}')

    yMax = max(Hist.Bins)
#  print 'Bins: ' + str(Hist.Bins)
#  print 'Bin Sum: ' + str(sum(Hist.Bins))

    # print Hist.Bins
    plt.clf()
    plt.bar(BinValues, Hist.Bins, color='blue', edgecolor=None, linewidth=0, width=Hist.BinWidth)
    plt.title(Title)
    plt.ylabel(ylabel)
    plt.xlabel(xlabel)
    # plt.xticks([])
    plt.yticks([])
    
    
    # For a time ticks were rendering very slowly, this turned out to be specific to numpy.linalg.inv on Python 2.7.6

    if ShowCutoffs:
        if MinCutoff:
            plt.plot([MinCutoff, MinCutoff], [0, yMax], color='red')

            if MinCutoffPercent:
                plt.annotate(f'{float(MinCutoffPercent) * 100:.3f}%', [MinCutoff, yMax * 0.5])

        if MaxCutoff:
            plt.plot([MaxCutoff, MaxCutoff], [0, yMax], color='red')

            if MaxCutoffPercent:
                plt.annotate(f'{((1 - float(MaxCutoffPercent)) * 100):.3f}%', [MaxCutoff, yMax * 0.5])


    if ShowLine:
        color = 'green'
        if not LineColorList is None:
            if not isinstance(LineColorList, Iterable):
                color = LineColorList
                
        for i, linePos in enumerate(LinePosList):
            if isinstance(LineColorList, Iterable) and len(LinePosList) >= i:
                color = LineColorList[i]
                    
            plt.plot([linePos, linePos], [0, yMax], color=color)
            plt.annotate(f'{linePos:g}', [linePos, yMax * 0.9])
            
    plt.gcf().set_dpi(150)

    visible_min_x, visible_max_x = None, None
    if minX is None or maxX is None:
        
        width_pixels, height_pixels = GetPlotSizeInPixels(plt.gcf(), plt.gca())
        #If we do not have enough horizontal space to display the entire histogram, attempt to trim it to the visible region
        if width_pixels < (Hist.MaxValue - Hist.MinValue) / Hist.BinWidth:
            visible_min_x, visible_max_x = Hist.XAxis_Extrema_Using_Threshold(height_pixels)
        else:
            visible_min_x, visible_max_x = Hist.MinValue, Hist.MaxValue

    if minX is None:
        options = LinePosList + [visible_min_x]
        minX = min(options)

    if maxX is None:
        options = LinePosList + [visible_max_x]
        maxX = max(options)
    
    #adjust range to a power of two 
    if range_is_power_of_two:
        minX, maxX = EnsureAxisLimitsArePowerOfTwo(minX, maxX)
        
    plt.xlim([minX - Hist.BinWidth, maxX + Hist.BinWidth])

    if ImageFilename is not None:
        # plt.show() 
        plt.savefig(ImageFilename,  bbox_inches='tight', dpi=dpi)
        plt.close()
    else:
        plt.show()
        
def GetPlotSizeInPixels(fig, ax) -> tuple[float, float]:
    bbox = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
    return bbox.bounds[2] * fig.dpi, bbox.bounds[3] * fig.dpi
        
def EnsureAxisLimitsArePowerOfTwo(min_val: float, max_val: float) -> tuple[float, float]:
    """
    Given a range, expands the range to be the nearest power of two, with a preference
    towards making the minimum value of the range 0 if possible
    """
    range = max_val - min_val
    power_of_two = nornir_imageregistration.NearestPowerOfTwo(range)
    extra_range = power_of_two - range
    #If we can set the min_val to 0, then do so and use remaining range to increase 
    #the max value
    if min_val - extra_range <= 0:
        min_val = min_val - extra_range
        extra_range = -min_val
        min_val = 0
        max_val = max_val + extra_range
    else: #Apply extra range equally to both min/max values
        extra_range_half = extra_range / 2.0
        min_val -= extra_range_half
        max_val += extra_range_half
        
    return min_val, max_val
    

def Scatter(x, y, s=None, c=None, Title: str | None = None,
            XAxisLabel: str | None = None, YAxisLabel: str | None =None,
            OutputFilename: str | None = None, **kwargs):

    if s is None:
        s = 7
    
    if not 'marker' in kwargs:
        kwargs['marker'] = 'o'
    
    plt.cla()
    fig, ax = plt.subplots()
    
    ax.scatter(x, y, s=s, c=c, edgecolor=None, **kwargs)

    if not Title is None:
        ax.set_title(Title)
    if not YAxisLabel is None:
        ax.set_ylabel(YAxisLabel)
    if not XAxisLabel is None:
        ax.set_xlabel(XAxisLabel)

    ax.set_xlim(0, max(x) + 1)
    ax.set_ylim(0, max(y) + 1)
    
    SetSquareAspectRatio(ax)
    
    if OutputFilename is not None:
        plt.ioff()
        if isinstance(OutputFilename, str):
            plt.savefig(OutputFilename)
        else:
            for filename in OutputFilename:
                plt.savefig(filename)
    else:
        plt.show()
        
    plt.close()

class ColorSelectionStyle(Enum):
    ''' Methods of assigning color to separate lines in PolyLine() '''
    BY_LINE_LENGTH = 0
    PER_LINE = 1

def PolyLine(PolyLineList, Title=None, XAxisLabel=None, YAxisLabel=None, OutputFilename=None, xlim=None, ylim=None, XTicks=None, XTickLabels=None, XTickRotation=None, YTicks=None, YTickLabels=None, YTickRotation=None, Colors=None, ColorStyle=ColorSelectionStyle.BY_LINE_LENGTH, **kwargs):
    '''PolyLineList is a nested list in this form:
    lines:
        line1:
            xAxis: x1, x2, x3, ...
            yAxis: y1, y2, y3, ...
        line2:
            xAxis: ...
            yAxis: ...
        ...
    '''

    # Default line color scheme
    if Colors is None:
        Colors = ['black', 'blue', 'green', 'yellow', 'orange', 'red', 'purple']

    # Use + as the default point marker. NOTE: We may wish to let matplotlib use its own default instead.
    if not 'marker' in kwargs:
        kwargs['marker'] = '+'

    if not 'markersize' in kwargs:
        kwargs['markersize'] = 5

    if not 'alpha' in kwargs:
        kwargs['alpha'] = 0.5

    # print Hist.Bins
    plt.cla()
    fig, ax = plt.subplots()
    
    num = 0
    for line in PolyLineList:
        colorVal = 'black'

        if ColorStyle == ColorSelectionStyle.BY_LINE_LENGTH:
            numPoints = len(line[0])
            if numPoints < len(Colors):
                colorVal = Colors[numPoints]
        elif ColorStyle == ColorSelectionStyle.PER_LINE:
            if len(Colors) > num:
                colorVal = Colors[num]

        num += 1

        # Copy kwargs for each line so the following assignments don't cause the first color to be used for all lines
        line_kwargs = kwargs.copy()
        
        # If markerfacecolor or markeredgecolor are specified, override PolyLine()'s colors argument.
        if not 'markerfacecolor' in line_kwargs:
            line_kwargs['markerfacecolor'] = colorVal

        if not 'markeredgecolor' in line_kwargs:
            line_kwargs['markeredgecolor'] = colorVal

        ax.plot(line[0], line[1], color=colorVal, **kwargs)

    if not Title is None:
        ax.set_title(Title)
    if not YAxisLabel is None:
        ax.set_ylabel(YAxisLabel)
    if not XAxisLabel is None:
        ax.set_xlabel(XAxisLabel)
        
    if xlim is not None:
        ax.set_xlim(xlim)
        
    if ylim is not None:
        ax.set_ylim(ylim)

    # Note: Matplotlib doesn't allow labels to be specified without locations,
    # so XTickLabels will be ignored unless XTicks is present
    # (The same is true for YTicks)

    if XTicks is not None:
        ax.set_xticks(ticks=XTicks, labels=XTickLabels, rotation=XTickRotation)

    if YTicks is not None:
        ax.set_yticks(ticks=YTicks, labels=YTickLabels, rotation=YTickRotation)
        
    SetSquareAspectRatio(ax)

    if OutputFilename is not None:
        plt.ioff()
        if isinstance(OutputFilename, str):
            plt.savefig(OutputFilename)
        else:
            for filename in OutputFilename:
                plt.savefig(filename)
    else:
        plt.show()
        
    plt.close()
    
    
def __PlotVectorOriginShape(render_mask, shape, Points, weights=None, color=None, colormap=None):
    '''Plot a subset of the points that are True in the mask with the specified shape
    color is only used if weights is none.
    '''
     
    if weights is None:
        if color is None:
            color = 'red' 
        
        plt.scatter(Points[:, 1], Points[:, 0], color=color, marker=shape, alpha=0.5)
    else:
        if colormap is None:
            colormap = plt.get_cmap('RdYlBu')
        
        plt.scatter(Points[render_mask, 1], Points[render_mask, 0], c=weights[render_mask], marker=shape, vmin=0, vmax=max(weights), alpha=0.5, cmap=colormap)
    

def VectorField(Points: NDArray, Offsets, shapes=None, weights=None,
                OutputFilename: str | None = None,
                ylim: tuple[float, float] | None = None,
                xlim: tuple[float, float] | None = None, colors=None):
     
    plt.clf() 
    
    if shapes is None:
        shapes = 's'
         
    if isinstance(shapes, str):
        shapes = shapes
        mask = numpy.ones(Points.shape[0], dtype=numpy.bool)
        __PlotVectorOriginShape(mask, shapes, Points, weights)
    else:
        try:
            _ = iter(shapes)
        except TypeError:
            raise ValueError("shapes must be None, string, or iterable type")
    
        #Iterable
        if len(shapes) != Points.shape[0]:
            raise ValueError("Length of shapes must match number of points")
        
        #Plot each batch of points with different shape
        all_shapes = set(shapes)
        
        for shape in all_shapes:
            mask = [s == shape for s in shapes]
            mask = numpy.asarray(mask, dtype=bool)
            
            __PlotVectorOriginShape(mask, shape, Points, weights, color=colors)
            
    if ylim is not None:
        plt.ylim(ylim)
        
    if xlim is not None:
        plt.xlim(xlim)
             
    if weights is not None:
        plt.colorbar()
    
    assert(Points.shape[0] == Offsets.shape[0])
    for iRow in range(0, Points.shape[0]):
        Origin = Points[iRow, :]
        scaled_offset = Offsets[iRow, :]
         
        Destination = Origin + scaled_offset
         
        line = numpy.vstack((Origin, Destination))
        plt.plot(line[:, 1], line[:, 0], color='blue')
         
    if OutputFilename is not None:
        if isinstance(OutputFilename, str):
            plt.savefig(OutputFilename, dpi=300)
        else:
            for filename in OutputFilename:
                plt.savefig(filename, dpi=300)
    else:
        plt.show()


if __name__ == '__main__':
    # Executed as a script, call the histogram function
    args = ProcessArgs()
    Histogram(HistogramOrFilename=args.HistogramFilename, ImageFilename=args.ImageFilename, MinCutoffPercent=args.MinCutoffPercent, MaxCutoffPercent=args.MaxCutoffPercent, LinePosList=args.LinePosition)

    prettyoutput.Log(args)
