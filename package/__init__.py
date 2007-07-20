"""
IGraph library.

@undocumented: test
"""

__license__ = """
Copyright (C) 2006-2007  Gabor Csardi <csardi@rmki.kfki.hu>,
Tamas Nepusz <ntamas@rmki.kfki.hu>

MTA RMKI, Konkoly-Thege Miklos st. 29-33, Budapest 1121, Hungary

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc.,  51 Franklin Street, Fifth Floor, Boston, MA 
02110-1301 USA
"""

from core import *
from core import __version__, __build_date__
from clustering import *
from layout import *
from drawing import *
from configuration import Configuration

import os
import math
import gzip
import sys
from tempfile import mkstemp
from warnings import warn

def summary(o, f=sys.stdout):
    """Prints a summary of object o to a given stream

    @param o: the object about which a human-readable summary is requested.
    @param f: the stream to be used
    """
    if hasattr(o, "summary"):
        print >>f, o.summary()
    else:
        print >>f, str(o)


class Graph(core.GraphBase):
    """Generic graph.
    
    This class is built on top of L{GraphBase}, so the order of the
    methods in the Epydoc documentation is a little bit obscure:
    inherited methods come after the ones implemented directly in the
    subclass. L{Graph} provides many functions that L{GraphBase} does not,
    mostly because these functions are not speed critical and they were
    easier to implement in Python than in pure C. An example is the
    attribute handling in the constructor: the constructor of L{Graph}
    accepts three dictionaries corresponding to the graph, vertex and edge
    attributes while the constructor of L{GraphBase} does not. This extension
    was needed to make L{Graph} serializable through the C{pickle} module.
    """

    # Some useful aliases
    omega = core.GraphBase.clique_number
    alpha = core.GraphBase.independence_number
    shell_index = core.GraphBase.coreness

    def __init__(self, n=1, edges=None, directed=None, \
        graph_attrs=None, vertex_attrs=None, edge_attrs=None):
        """Constructs a graph from scratch.

        @param n: the number of vertices. Can be omitted.
        @param edges: the edge list where every list item is a pair of integers.
            If any of the integers is larger than M{n-1}, the number of vertices
            is adjusted accordingly.
        @param directed: whether the graph should be directed
        @param graph_attrs: the attributes of the graph as a dictionary.
        @param vertex_attrs: the attributes of the vertices as a dictionary.
        	Every dictionary value must be an iterable with exactly M{n} items.
        @param edge_attrs: the attributes of the edges as a dictionary. Every
        	dictionary value must be an iterable with exactly M{m} items where
            M{m} is the number of edges.
        """
        # Check if n is a list. If so, that means that the number of vertices
        # were omitted, so we should shift the whole parameter list with 1.
        if isinstance(n, list) or isinstance(n, tuple):
            edge_attrs = vertex_attrs
            vertex_attrs = graph_attrs
            graph_attrs = directed
            directed = edges
            edges = n
            n = 1
        edges = edges or []
        directed = directed or False
        graph_attrs = graph_attrs or {}
        vertex_attrs = vertex_attrs or {}
        edge_attrs = edge_attrs or {}
        core.GraphBase.__init__(self, n, edges, directed)
        # Set the graph attributes
        for k, v in graph_attrs.iteritems():
            if isinstance(k, int) or isinstance(k, long): k=str(k)
            self[k]=v
        # Set the vertex attributes
        for k, v in vertex_attrs.iteritems():
            if isinstance(k, int) or isinstance(k, long): k=str(k)
            self.vs[k]=v
        # Set the edge attributes
        for k, v in edge_attrs.iteritems():
            if isinstance(k, int) or isinstance(k, long): k=str(k)
            self.es[k]=v

    def indegree(self, *args, **kwds):
        """Returns the in-degrees in a list.
        
        See L{degree} for possible arguments.
        """
        kwds['degree']=_igraph.IN
        return self.degree(*args, **kwds)

    def outdegree(self, *args, **kwds):
        """Returns the out-degrees in a list.
        
        See L{degree} for possible arguments.
        """
        kwds['degree']=_igraph.OUT
        return self.degree(*args, **kwds)

    def eccentricity(self, nodes=None):
        """Calculates eccentricities for vertices with the given indices.
        
        Eccentricity is given as the reciprocal of the greatest distance
        between the vertex being considered and any other vertex in the
        graph.

        Please note that for any unconnected graph, eccentricities will
        all be equal to 1 over the number of vertices, since for all vertices
        the greatest distance will be equal to the number of vertices (this
        is how L{shortest_paths} denotes vertex pairs where it is impossible
        to reach one from the other).

        @param vertices: the vertices to consider. If C{None}, all
          vertices are considered.
        @return: the eccentricities in a list
        """
        if self.vcount() == 0: return []
        if self.vcount() == 1: return [1.0]
        distance_matrix = self.shortest_paths(mode=OUT)
        distance_maxs = map(max, distance_matrix)
        
        if nodes is None:
            result = [1.0/x for x in distance_maxs]
        else:
            result = [1.0/distance_maxs[idx] for idx in nodes]

        return result

    def clusters(self, mode=STRONG):
        """clusters(mode=STRONG)

        Calculates the (strong or weak) clusters (connected components) for
        a given graph.

        @param mode: must be either C{STRONG} or C{WEAK}, depending on the
          clusters being sought. Optional, defaults to C{STRONG}.
        @return: a L{VertexClustering} object"""
        return VertexClustering(self, GraphBase.clusters(self, mode))
    components = clusters

    def degree_distribution(self, bin_width = 1, *args, **kwds):
        """degree_distribution(bin_width=1, ...)

        Calculates the degree distribution of the graph.

        Unknown keyword arguments are directly passed to L{degree()}.

        @param bin_width: the bin width of the histogram
        @return: a histogram representing the degree distribution of the
          graph.
        """
        result = Histogram(bin_width, self.degree(*args, **kwds))
        return result

    def modularity(self, membership):
        """modularity(membership)

        Calculates the modularity score of the graph with respect to a given
        clustering.
        
        The modularity of a graph w.r.t. some division measures how good the
        division is, or how separated are the different vertex types from each
        other. It is defined as M{Q=1/(2m)*sum(Aij-ki*kj/(2m)delta(ci,cj),i,j)}.
        M{m} is the number of edges, M{Aij} is the element of the M{A} adjacency
        matrix in row M{i} and column M{j}, M{ki} is the degree of node M{i},
        M{kj} is the degree of node M{j}, and M{Ci} and C{cj} are the types of
        the two vertices (M{i} and M{j}). M{delta(x,y)} is one iff M{x=y}, 0
        otherwise.

        @param membership: a membership list or a L{VertexClustering} object
        @return: the modularity score
        
        @newfield ref: Reference
        @ref: MEJ Newman and M Girvan: Finding and evaluating community
          structure in networks. Phys Rev E 69 026113, 2004.
        """
        if isinstance(membership, VertexClustering):
            if membership.graph != self:
                raise ValueError, "clustering object belongs to a different graph"
            return GraphBase.modularity(self, membership.membership)
        else:
            return GraphBase.modularity(self, membership)

    # Various clustering algorithms -- mostly wrappers around GraphBase

    def community_fastgreedy(self):
        """Community structure based on the greedy optimization of modularity.

        This algorithm merges individual nodes into communities in a way that
        greedily maximizes the modularity score of the graph. It can be proven
        that if no merge can increase the current modularity score, the algorithm
        can be stopped since no further increase can be achieved.

        This algorithm is said to run almost in linear time on sparse graphs.

        @return: an appropriate L{VertexClustering} object.

        @newfield ref: Reference
        @ref: A Clauset, MEJ Newman and C Moore: Finding community structure
          in very large networks. Phys Rev E 70, 066111 (2004).
        """
        merges, qs = GraphBase.community_fastgreedy(self, True)
        return VertexDendrogram(self, merges, None, qs)


    def community_leading_eigenvector_naive(self, clusters=None, return_merges = False):
        """community_leading_eigenvector_naive(clusters=None, return_merges=False)
        A naive implementation of Newman's eigenvector community structure
        detection. This function splits the network into two components
        according to the leading eigenvector of the modularity matrix and
        then recursively takes the given number of steps by splitting the
        communities as individual networks. This is not the correct way,
        however, see the reference for explanation. Consider using the
        correct L{community_leading_eigenvector} method instead.

        @param clusters: the desired number of communities. If C{None}, the algorithm
          tries to do as many splits as possible. Note that the algorithm
          won't split a community further if the signs of the leading eigenvector
          are all the same, so the actual number of discovered communities can be
          less than the desired one.
        @param return_merges: whether the returned L{VertexClustering} object
          should contain information about the merges performed on the graph.
        @return: an appropriate L{VertexClustering} object.
        @param return_merges: whether 
        
        @newfield ref: Reference
        @ref: MEJ Newman: Finding community structure in networks using the
        eigenvectors of matrices, arXiv:physics/0605087"""
        if clusters is None: clusters=-1
        cl, merges = GraphBase.community_leading_eigenvector_naive(self, clusters, return_merges)
        if merges is None:
            return VertexClustering(self, cl)
        else:
            return VertexDendrogram(self, merges, cl)


    def community_leading_eigenvector(self, clusters=None, return_merges = False):
        """community_leading_eigenvector(clusters=None, return_merges=False)
        
        Newman's leading eigenvector method for detecting community structure.
        This is the proper implementation of the recursive, divisive algorithm:
        each split is done by maximizing the modularity regarding the
        original network.
        
        @param clusters: the desired number of communities. If C{None}, the algorithm
          tries to do as many splits as possible. Note that the algorithm
          won't split a community further if the signs of the leading eigenvector
          are all the same, so the actual number of discovered communities can be
          less than the desired one.
        @param return_merges: whether the returned L{VertexClustering} object
          should contain information about the merges performed on the graph.
        @return: an appropriate L{VertexClustering} object.
        @param return_merges: whether 
        
        @newfield ref: Reference
        @ref: MEJ Newman: Finding community structure in networks using the
        eigenvectors of matrices, arXiv:physics/0605087"""
        if clusters is None: clusters=-1
        cl, merges = GraphBase.community_leading_eigenvector(self, clusters, return_merges)
        if merges is None:
            return VertexClustering(self, cl)
        else:
            return VertexDendrogram(self, merges, cl)


    def community_edge_betweenness(self, clusters = None, directed = True):
        """Community structure based on the betweenness of the edges in the network.

        The idea is that the betweenness of the edges connecting two communities
        is typically high, as many of the shortest paths between nodes in separate
        communities go through them. So we gradually remove the edge with the
        highest betweenness and recalculate the betweennesses after every
        removal. This way sooner or later the network falls of to separate
        components. The result of the clustering will be represented by a
        dendrogram.

        @param clusters: the number of clusters we would like to see. This
          practically defines the "level" where we "cut" the dendrogram to
          get the membership vector of the vertices. If C{None}, the dendrogram
          is cut at the level which maximizes the modularity.
        @param directed: whether the directionality of the edges should be taken
          into account or not.
        @return: a L{VertexClustering} object. Besides the usual methods and members,
          this object will have a member called C{merges} which records information
          used to produce the dendrogram. It is practically a list of tuples where
          each tuple defines two nodes which will be joined in a step. Node IDs
          from 0 to M{n-1} (where M{n} is the number of vertices) correspond to
          the individual vertices, while node IDs up from M{n} correspond to
          merged communities. M{n} means the community created after the first
          merge, M{n+1} means the community created after the second merge and
          so on...
        """
        d = VertexDendrogram(self, GraphBase.community_edge_betweenness(self, directed));
        if clusters is not None: d.cut(clusters)
        return d
    
    def edge_betweenness_clustering(self, clusters = None, steps = None):
        """Newman's edge betweenness clustering.

        Iterative removal of edges with the largest edge betweenness until
        the given number of steps is reached or until the graph is decomposed
        to the given number of clusters. Edge betweennesses are recalculated
        after every run.

        @param clusters: the desired number of clusters.
        @param steps: the number of tests to take.

        @return: an appropriate L{VertexClustering} object.

        @newfield ref: Reference
        @ref: Girvan, M and Newman, MEJ: Community structure in social and
          biological networks. Proc. Natl. Acad. Sci. USA 99, 7821-7826 (2002)
        """
        warn("Graph.edge_betweenness_clustering is deprecated and will be removed soon. Use Graph.community_edge_betweenness instead", DeprecationWarning)
        g = self.copy()
        number_of_steps = 0

        directed = g.is_directed()

        while True:
            if clusters is not None:
                cl = g.clusters()
                if max(cl)+1 >= clusters: break

            if steps is not None:
                if number_of_steps > steps: break

            ebs = g.edge_betweenness(directed)

            if len(ebs) == 0: break

            eb_max = max(ebs)
            eb_max_index = ebs.index(eb_max)

            g.delete_edges(eb_max_index, by_index=True)
            number_of_steps += 1

        return VertexClustering(self, g.clusters()) 


    def k_core(self, *args):
        """Returns some k-cores of the graph.

        The method accepts an arbitrary number of arguments representing
        the desired indices of the M{k}-cores to be returned. The arguments
        can also be lists or tuples. The result is a single L{Graph} object
        if an only integer argument was given, otherwise the result is a
        list of L{Graph} objects representing the desired k-cores in the
        order the arguments were specified. If no argument is given, returns
        all M{k}-cores in increasing order of M{k}.
        """
        if len(args) == 0:
            indices = xrange(self.vcount())
            return_single = False
        else:
            return_single = True
            indices = []
            for arg in args:
                try:
                    indices.extend(arg)
                except:
                    indices.append(arg)

        if len(indices)>1 or hasattr(args[0], "__iter__"):
            return_single = False

        corenesses = self.coreness()
        result = []
        vidxs = xrange(self.vcount())
        for idx in indices:
            core_idxs = [vidx for vidx in vidxs if corenesses[vidx] >= idx]
            result.append(self.subgraph(core_idxs))

        if return_single: return result[0]
        return result


    def layout(self, layout=None, *args, **kwds):
        """Returns the layout of the graph according to a layout algorithm.

        Parameters and keyword arguments not specified here are passed to the
        layout algorithm directly. See the documentation of the layout
        algorithms for the explanation of these parameters.

        Registered layout names understood by this method are:

          * C{circle}, C{circular}: circular layout (see L{Graph.layout_circle})
          * C{fr}, C{fruchterman_reingold}: Fruchterman-Reingold layout
            (see L{Graph.layout_fruchterman_reingold}).
          * C{fr_3d}, C{fr3d}, C{fruchterman_reingold_3d}: 3D Fruchterman-Reingold
            layout (see L{Graph.layout_fruchterman_reingold_3d}).
          * C{gfr}, C{grid_fr}, C{grid_fruchterman_reingold}: grid-based
            Fruchterman-Reingold layout
            (see L{Graph.layout_grid_fruchterman_reingold})
          * C{kk}, C{kamada_kawai}: Kamada-Kawai layout
            (see L{Graph.layout_kamada_kawai}).
          * C{kk_3d}, C{kk3d}, C{kamada_kawai_3d}: 3D Kamada-Kawai layout
            (see L{Graph.layout_kamada_kawai_3d}).
          * C{lgl}, C{large}, C{large_graph}: Large Graph Layout
            (see L{Graph.layout_lgl})
          * C{random}: random layout (see L{Graph.layout_random})
          * C{random_3d}: random 3D layout (see L{Graph.layout_random_3d})
          * C{rt}, C{tree}, C{reingold_tilford}: Reingold-Tilford tree
            layout (see L{Graph.layout_reingold_tilford}).
          * C{sphere}, C{spherical}, C{circle_3d}, C{circular_3d}: spherical
            layout (see L{Graph.layout_sphere})

        @param layout: the layout to use. This can be one of the registered
          layout names or a callable which returns either a L{Layout} object or
          a list of lists containing the coordinates. If C{None}, uses the
          value of the C{plotting.layout} configuration key.
        @return: a L{Layout} object.
        """
        if layout is None: layout = config["plotting.layout"]
        if callable(layout):
            method = layout
        else:
            method = getattr(self.__class__, self._layout_mapping[layout])
        if not callable(method): raise ValueError, "layout method must be callable"
        l=method(self, *args, **kwds)
        if not isinstance(l, Layout): l=Layout(l)
        return l

    def write_graphmlz(self, f, compresslevel=9):
        """Writes the graph to a zipped GraphML file.

        The library uses the gzip compression algorithm, so the resulting
        file can be unzipped with regular gzip uncompression (like
        C{gunzip} or C{zcat} from Unix command line) or the Python C{gzip}
        module.

        Uses a temporary file to store intermediate GraphML data, so
        make sure you have enough free space to store the unzipped
        GraphML file as well.

        @param f: the name of the file to be written.
        @param compresslevel: the level of compression. 1 is fastest and
          produces the least compression, and 9 is slowest and produces
          the most compression."""
        tmpfilename=None
        try:
            tmpfileno, tmpfilename = mkstemp(text=True)
            os.close(tmpfileno)
            self.write_graphml(tmpfilename)
            outf = gzip.GzipFile(f, "wb", compresslevel)
            inf = open(tmpfilename)
            for line in inf: outf.write(line)
            inf.close()
            outf.close()
        finally:
            if tmpfilename is not None: os.unlink(tmpfilename)

    def Read_GraphMLz(cls, f, *params, **kwds):
        """Read_GraphMLz(f, directed=True, index=0)

        Reads a graph from a zipped GraphML file.

        @param f: the name of the file
        @param index: if the GraphML file contains multiple graphs,
          specified the one that should be loaded. Graph indices
          start from zero, so if you want to load the first graph,
          specify 0 here.
        @return: the loaded graph object"""
        tmpfilename=None
        try:
            tmpfileno, tmpfilename = mkstemp(text=True)
            os.close(tmpfileno)
            inf = gzip.GzipFile(f, "rb")
            outf = open(tmpfilename, "wt")
            for line in inf: outf.write(line)
            inf.close()
            outf.close()
            result=cls.Read_GraphML(tmpfilename)
        finally:
            if tmpfilename is not None: os.unlink(tmpfilename)
        return result
    Read_GraphMLz = classmethod(Read_GraphMLz)


    def write_pickle(self, fname=None, version=-1):
        """Saves the graph in Python pickled format

        @param fname: the name of the file or a stream to save to. If
          C{None}, saves the graph to a string and returns the string.
        @param version: pickle protocol version to be used. If -1, uses
          the highest protocol available
        @return: C{None} if the graph was saved successfully to the
          file given, or a string if C{fname} was C{None}.
        """
        import cPickle
        if fname is None: return cPickle.dumps(self, version)
        if not isinstance(fname, file):
            file_was_opened=True
            fname=open(fname, 'wb')
        result=cPickle.dump(self, fname, version)
        if file_was_opened: fname.close()
        return result


    def Read_Pickle(klass, fname=None):
        """Reads a graph from Python pickled format

        @param fname: the name of the file, a stream to read from, or
          a string containing the pickled data. The string is assumed to
          hold pickled data if it is longer than 40 characters and
          contains the substring C{cigraph\nGraph\n}.
        @return: the created graph object.
        """
        import cPickle
        if len(fname)>40 and "cigraph\nGraph\n" in fname:
            return cPickle.loads(fname)
        if not isinstance(fname, file):
            file_was_opened=True
            fname=open(fname, 'rb')
        result=cPickle.load(fname)
        if file_was_opened: fname.close()
        if not isinstance(result, klass):
            raise TypeError, "unpickled object is not a %s" % klass.__name__
        return result
    Read_Pickle = classmethod(Read_Pickle)

    def write_svg(self, fname, layout, width = None, height = None, \
                  labels = "label", colors = "color", shapes = "shape", \
                  vertex_size = 10, edge_colors = "color", \
		  font_size = 16, *args, **kwds):
        """Saves the graph as an SVG (Scalable Vector Graphics) file
        
        @param fname: the name of the file
        @param layout: the layout of the graph. Can be either an
          explicitly specified layout (using a list of coordinate
          pairs) or the name of a layout algorithm (which should
          refer to a method in the L{Graph} object, but without
          the C{layout_} prefix.
        @param width: the preferred width in pixels (default: 400)
        @param height: the preferred height in pixels (default: 400)
        @param labels: the vertex labels. Either it is the name of
          a vertex attribute to use, or a list explicitly specifying
          the labels. It can also be C{None}.
        @param colors: the vertex colors. Either it is the name of
          a vertex attribute to use, or a list explicitly specifying
          the colors. A color can be anything acceptable in an SVG
          file.
        @param shapes: the vertex shapes. Either it is the name of
          a vertex attribute to use, or a list explicitly specifying
          the shapes as integers. Shape 0 means hidden (nothing is drawn),
          shape 1 is a circle, shape 2 is a rectangle.
        @param vertex_size: vertex size in pixels
	@param edge_colors: the edge colors. Either it is the name
	  of an edge attribute to use, or a list explicitly specifying
	  the colors. A color can be anything acceptable in an SVG
	  file.
        @param font_size: font size. If it is a string, it is written into
          the SVG file as-is (so you can specify anything which is valid
          as the value of the C{font-size} style). If it is a number, it
          is interpreted as pixel size and converted to the proper attribute
          value accordingly.
        """
        if width is None and height is None:
            width = 400
            height = 400
        elif width is None:
            width = height
        elif height is None:
            height = width
                
        if width<=0 or height<=0:
            raise ValueError, "width and height must be positive"

        if isinstance(layout, str):
            f=getattr(Graph, "layout_"+layout);
            layout=f(self, *args)

        if isinstance(labels, str):
            try:
                labels = self.vs.get_attribute_values(labels)
            except KeyError:
                labels = [x+1 for x in xrange(self.vcount())]
        elif labels is None:
            labels = [""] * self.vcount()

        if isinstance(colors, str):
            try:
                colors = self.vs.get_attribute_values(colors)
            except KeyError:
                colors = ["red" for x in xrange(self.vcount())]

        if isinstance(shapes, str):
            try:
                shapes = self.vs.get_attribute_values(shapes)
            except KeyError:
                shapes = [1]*self.vcount()
        
	if isinstance(edge_colors, str):
	    try:
		edge_colors = self.es.get_attribute_values(edge_colors)
	    except KeyError:
		edge_colors = ["black" for x in xrange(self.ecount())]
		
        if not isinstance(font_size, str):
            font_size = "%spx" % str(font_size)
        else:
            if ";" in font_size:
                raise ValueError, "font size can't contain a semicolon"

        vc = self.vcount()
        while len(labels)<vc: labels.append(len(labels)+1)
        while len(colors)<vc: colors.append("red")

        f=open(fname, "w")
                
        maxs=[layout[0][dim] for dim in range(2)]
        mins=[layout[0][dim] for dim in range(2)]
                
        for rowidx in range(1, len(layout)):
            row = layout[rowidx]
            for dim in range(0, 2):
                if maxs[dim]<row[dim]: maxs[dim]=row[dim]
                if mins[dim]>row[dim]: mins[dim]=row[dim]
                
        sizes=[width-2*vertex_size, height-2*vertex_size]
        halfsizes=[(maxs[dim]+mins[dim])/2.0 for dim in range(2)]
        ratios=[sizes[dim]/(maxs[dim]-mins[dim]) for dim in range(2)]
        layout=[[(row[0]-halfsizes[0])*ratios[0], \
                 (row[1]-halfsizes[1])*ratios[1]] \
                for row in layout]
		
	directed=self.is_directed()

        print >>f, "<?xml version=\"1.0\" standalone=\"no\"?>"
        print >>f, "<!DOCTYPE svg PUBLIC \"-//W3C//DTD SVG 1.1//EN\""
        print >>f, "\"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd\">"
        
        print >>f, "<svg width=\"%d\" height=\"%d\" version=\"1.1\" xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\">" % (width, height)
        print >>f, "<!-- Created by igraph -->"
        print >>f
        print >>f, "<defs>"
        print >>f, "  <symbol id=\"Triangle\" overflow=\"visible\">"
        print >>f, "    <path d=\"M 0 0 L 10 -5 L 10 5 z\"/>"
        print >>f, "  </symbol>"
        print >>f, "  <style type=\"text/css\">"
        print >>f, "    <![CDATA["
        print >>f, "#vertices circle { stroke: black; stroke-width: 1 }"
        print >>f, "#vertices rect { stroke: black; stroke-width: 1 }"
        print >>f, "#vertices text { text-anchor: middle; font-size: %s; font-family: sans-serif; font-weight: normal }" % font_size
	print >>f, "#edges line { stroke-width: 1 }"
        print >>f, "    ]]>"
        print >>f, "  </style>"
        print >>f, "</defs>"
        print >>f
        print >>f, "<g transform=\"translate(%.4f,%.4f)\">" % (width/2.0, height/2.0)
        print >>f, "  <g id=\"edges\">"
        print >>f, "  <!-- Edges -->"

        has_edge_opacities = "opacity" in self.edge_attributes()
        for eidx, edge in enumerate(self.es):
            vidxs = edge.tuple
            x1 = layout[vidxs[0]][0]
            y1 = layout[vidxs[0]][1]
            x2 = layout[vidxs[1]][0]
            y2 = layout[vidxs[1]][1]
            angle = math.atan2(y2-y1, x2-x1)
            x2 = x2 - vertex_size*math.cos(angle)
            y2 = y2 - vertex_size*math.sin(angle)
	    if directed:
		# Dirty hack because the SVG specification: markers do not inherit stroke colors
		print >>f, "    <g transform=\"translate(%.4f,%.4f)\" fill=\"%s\" stroke=\"%s\">" % (x2, y2, edge_colors[eidx], edge_colors[eidx]) 
		print >>f, "      <line x1=\"%.4f\" y1=\"%.4f\" x2=\"0\" y2=\"0\"/>" % (x1-x2, y1-y2)
		print >>f, "      <use x=\"0\" y=\"0\" xlink:href=\"#Triangle\" transform=\"rotate(%.4f)\"/>" % (180+angle*180/math.pi,)
		print >>f, "    </g>\n"
	    else:
		print >>f, "    <line x1=\"%.4f\" y1=\"%.4f\" x2=\"%.4f\" y2=\"%.4f\" style=\"stroke: %s\"/>" % (x1, y1, x2, y2, edge_colors[eidx])

        print >>f, "  </g>"
        print >>f

        print >>f, "  <g id=\"vertices\">"
        print >>f, "  <!-- Vertices -->"
        for vidx in range(self.vcount()):
            print >>f, "    <g transform=\"translate(%.4f %.4f)\">" % (layout[vidx][0], layout[vidx][1])
            if shapes[vidx] == 1:
                # Undocumented feature: can handle two colors
                c = str(colors[vidx])
                if " " in c:
                    c = c.split(" ")
                    vs = str(vertex_size)
                    print >>f, "      <path d=\"M -%s,0 A%s,%s 0 0,0 %s,0 L -%s,0\" fill=\"%s\"/>" % (vs,vs,vs,vs,vs,c[0])
                    print >>f, "      <path d=\"M -%s,0 A%s,%s 0 0,1 %s,0 L -%s,0\" fill=\"%s\"/>" % (vs,vs,vs,vs,vs,c[1])
                    print >>f, "      <circle cx=\"0\" cy=\"0\" r=\"%s\" fill=\"none\"/>" % vs
                else:
                    print >>f, "      <circle cx=\"0\" cy=\"0\" r=\"%s\" fill=\"%s\"/>" % (str(vertex_size), str(colors[vidx]))
            elif shapes[vidx] == 2:
                print >>f, "      <rect x=\"-%s\" y=\"-%s\" width=\"%s\" height=\"%s\" fill=\"%s\"/>" % (str(vertex_size), str(vertex_size), str(2*vertex_size), str(2*vertex_size), str(colors[vidx]))
            print >>f, "      <text x=\"0\" y=\"5\">%s</text>" % str(labels[vidx])
            print >>f, "    </g>"

        print >>f, "  </g>"
        print >>f, "</g>"
        print >>f
        print >>f, "</svg>"
                
        f.close()


    def _identify_format(klass, filename):
        """_identify_format(filename)

        Tries to identify the format of the graph stored in the file with the
        given filename. It identifies most file formats based on the extension
        of the file (and not on syntactic evaluation). The only exception is
        the adjacency matrix format and the edge list format: the first few
        lines of the file are evaluated to decide between the two.

        @note: Internal function, should not be called directly.

        @param filename: the name of the file or a file object whose C{name}
          attribute is set.
        @return: the format of the file as a string.
        """
        import os.path
        if isinstance(filename, file):
            try:
                filename=filename.name
            except:
                return None

        root, ext = os.path.splitext(filename)
        ext = ext.lower()
        
        if ext in [".graphml", ".graphmlz", ".lgl", ".ncol", ".pajek",
            ".gml", ".dimacs", ".edgelist", ".edges", ".edge", ".net",
            ".pickle"]:
            return ext[1:]

        if ext == ".txt" or ext == ".dat":
            # Most probably an adjacency matrix or an edge list
            f = open(filename, "r")
            line = f.readline()
            if line is None: return "edges"
            parts = line.strip().split()
            if len(parts) == 2:
                line = f.readline()
                if line is None: return "edges"
                parts = line.strip().split()
                if len(parts) == 2:
                    line = f.readline()
                    if line is None:
                        # This is a 2x2 matrix, it can be a matrix or an edge list
                        return None
                    else:
                        parts = line.strip().split()
                        if len(parts) == 0:
                            return None
                    return "edges"
                else:
                    # Not a matrix
                    return None
            else:
                return "adjacency"
    _identify_format = classmethod(_identify_format)
    
    
    def Read(klass, f, format=None, *args, **kwds):
        """Unified reading function for graphs.

        This method tries to identify the format of the graph given in
        the first parameter and calls the corresponding reader method.

        The remaining arguments are passed to the reader method without
        any changes.

        @param f: the file containing the graph to be loaded
        @param format: the format of the file (if known in advance).
          C{None} means auto-detection. Possible values are: C{"ncol"}
          (NCOL format), C{"lgl"} (LGL format), C{"graphml"}, C{"graphmlz"}
          (GraphML and gzipped GraphML format), C{"gml"} (GML format),
          C{"net"}, C{"pajek"} (Pajek format), C{"dimacs"} (DIMACS format),
          C{"edgelist"}, C{"edges"} or C{"edge"} (edge list),
          C{"adjacency"} (adjacency matrix), C{"pickle"} (Python pickled
          format).
        @raises IOError: if the file format can't be identified and
          none was given.
        """
        if format is None: format = klass._identify_format(f)
        try:
            reader = klass._format_mapping[format][0]
        except KeyError, IndexError:
            raise IOError, "unknown file format: %s" % str(format)
        if reader is None:
            raise IOError, "no reader method for file format: %s" % str(format)
        reader = getattr(klass, reader)
        return reader(f, *args, **kwds)
    Read = classmethod(Read)
    Load = Read

    
    def write(self, f, format=None, *args, **kwds):
        """Unified writing function for graphs.

        This method tries to identify the format of the graph given in
        the first parameter (based on extension) and calls the corresponding
        writer method.

        The remaining arguments are passed to the writer method without
        any changes.

        @param f: the file containing the graph to be saved
        @param format: the format of the file (if one wants to override the
          format determined from the filename extension, or the filename itself
          is a stream). C{None} means auto-detection. Possible values are: C{"ncol"}
          (NCOL format), C{"lgl"} (LGL format), C{"graphml"}, C{"graphmlz"}
          (GraphML and gzipped GraphML format), C{"gml"} (GML format),
          C{"net"}, C{"pajek"} (Pajek format), C{"dimacs"} (DIMACS format),
          C{"edgelist"}, C{"edges"} or C{"edge"} (edge list),
          C{"adjacency"} (adjacency matrix), C{"pickle"} (Python pickled
          format), C{"svg"} (Scalable Vector Graphics).
        @raises IOError: if the file format can't be identified and
          none was given.
        """
        if format is None: format = self._identify_format(f)
        try:
            writer = self._format_mapping[format][1]
        except KeyError, IndexError:
            raise IOError, "unknown file format: %s" % str(format)
        if writer is None:
            raise IOError, "no writer method for file format: %s" % str(format)
        writer = getattr(self, writer)
        return writer(f, *args, **kwds)
    save = write

    def __iadd__(self, other):
        """In-place addition (disjoint union).

        @see: L{__add__}
        """
        if isinstance(other, int):
            return self.add_vertices(other)
        elif isinstance(other, tuple) and len(other) == 2:
            return self.add_edges([other])
        elif isinstance(other, list):
            if len(other)>0:
                if isinstance(other[0], tuple):
                    return self.add_edges(other)
            else:
                return self

        return NotImplemented


    def __add__(self, other):
        """Copies the graph and extends the copy depending on the type of
        the other object given.

        @param other: if it is an integer, the copy is extended by the given
          number of vertices. If it is a tuple with two elements, the copy
          is extended by a single edge. If it is a list of tuples, the copy
          is extended by multiple edges. If it is a L{Graph}, a disjoint
          union is performed.
        """
        if isinstance(other, int):
            g = self.copy()
            g.add_vertices(other)
        elif isinstance(other, tuple) and len(other) == 2:
            g = self.copy()
            g.add_edges([other])
        elif isinstance(other, list):
            if len(other)>0:
                if isinstance(other[0], tuple):
                    g = self.copy()
                    g.add_edges(other)
                elif isinstance(other[0], Graph):
                    return self.disjoint_union(other)
                else:
                    return NotImplemented
            else:
                return self.copy()

        elif isinstance(other, Graph):
            return self.disjoint_union(other)
        else:
            return NotImplemented

        return g


    def __isub__(self, other):
        """In-place subtraction (difference).

        @see: L{__sub__}"""
        if isinstance(other, int):
            return self.delete_vertices(other)
        elif isinstance(other, tuple) and len(other) == 2:
            return self.delete_edges(other)
        elif isinstance(other, list):
            if len(other)>0:
                if isinstance(other[0], tuple):
                    return self.delete_edges(other)
                elif isinstance(other[0], int):
                    return self.delete_vertices(other)
            else:
                return self

        return NotImplemented


    def __sub__(self, other):
        """Removes the given object(s) from the graph

        @param other: if it is an integer, removes the vertex with the given
          ID from the graph (note that the remaining vertices will get
          re-indexed!). If it is a tuple, removes the given edge. If it is
          a graph, takes the difference of the two graphs. Accepts
          lists of integers or lists of tuples as well, but they can't be
          mixed!
        """
        if isinstance(other, int):
            return self.copy().delete_vertices(other)
        elif isinstance(other, tuple) and len(other) == 2:
            return self.copy().delete_edges(other)
        elif isinstance(other, list):
            if len(other)>0:
                if isinstance(other[0], tuple):
                    return self.copy().delete_edges(other)
                elif isinstance(other[0], int):
                    return self.copy().delete_vertices(other)
            else:
                return self.copy()
        elif isinstance(other, Graph):
            return self.difference(other)

        return NotImplemented

    def __mul__(self, other):
        """Copies exact replicas of the original graph an arbitrary number of times.

        @param other: if it is an integer, multiplies the graph by creating the
          given number of identical copies and taking the disjoint union of
          them.
        """
        if isinstance(other, int):
            if other == 0:
                return Graph()
            elif other == 1:
                return self
            elif other > 1:
                # TODO: should make it more efficient - powers of 2?
                return self.disjoint_union([self]*(other-1))
            else:
                return NotImplemented

        return NotImplemented
    
    def __coerce__(self, other):
        """Coercion rules.

        This method is needed to allow the graph to react to additions
        with lists, tuples or integers.
        """
        if type(other) in [int, tuple, list]:
            return self, other


    def __reduce__(self):
        """Support for pickling."""
        import warnings
        constructor = self.__class__
        graph_attr_names = self.attributes()
        vertex_attr_names = self.vs.attributes()
        edge_attr_names = self.es.attributes()
        gattrs, vattrs, eattrs = {}, {}, {}
        for a in graph_attr_names: gattrs[a] = self[a]
        for a in vertex_attr_names: vattrs[a] = self.vs[a]
        for a in edge_attr_names: eattrs[a] = self.es[a]
        parameters = (self.vcount(), self.get_edgelist(), self.is_directed(), \
            gattrs, vattrs, eattrs)
        return (constructor, parameters, {})


    def __plot__(self, context, bbox, *args, **kwds):
        """Plots the graph to the given Cairo context in the given bounding box
        
        TODO: documentation of keyword arguments
        """
        import drawing
        import cairo

        directed = self.is_directed()
        margin = kwds.get("margin", [0., 0., 0., 0.])
        try:
            margin = list(margin)
        except TypeError:
            margin = [margin]
        while len(margin)<4: margin.extend(margin)
        margin = tuple(map(float, margin[:4]))

        vertex_colors = drawing.collect_attributes(self.vcount(), "vertex_color", "color", kwds, self.vs, config, "red", drawing.color_to_rgb)
        vertex_sizes = drawing.collect_attributes(self.vcount(), "vertex_size", "size", kwds, self.vs, config, 10, float)
        max_vertex_size = max(vertex_sizes)

        layout = kwds.get("layout", None)
        if not isinstance(layout, Layout):
            layout = self.layout(layout)
        sl, st, sr, sb = layout.bounding_box()
        sw, sh = sr-sl, sb-st
        if sw == 0: sw=1
        if sh == 0: sh=1
        rx, ry = float(bbox.width-max_vertex_size-margin[1]-margin[3])/sw, \
          float(bbox.height-max_vertex_size-margin[0]-margin[2])/sh
        layout.scale(rx, ry)
        layout.translate(-sl*rx+max_vertex_size/2.+margin[1], \
          -st*ry+max_vertex_size/2.+margin[0])

        context.set_line_width(1)

        edge_colors = drawing.collect_attributes(self.ecount(), "edge_color", "color", kwds, self.es, config, "black", drawing.color_to_rgb)
        edge_widths = drawing.collect_attributes(self.ecount(), "edge_width", "width", kwds, self.es, config, 1, float)

        # Draw the edges
        for idx, e in enumerate(self.es):
            context.set_source_rgb(*edge_colors[idx])
            context.set_line_width(edge_widths[idx])

            src, tgt = e.tuple
            if src == tgt:
                # Loop edge
                r = vertex_sizes[src]*2
                cx, cy = layout[src][0]+math.cos(math.pi/4)*r/2, \
                  layout[src][1]-math.sin(math.pi/4)*r/2
                context.arc(cx, cy, r/2., 0, math.pi*2)
            else:
                context.move_to(*layout[src])
                context.line_to(*layout[tgt])
            context.stroke()

            if directed and src != tgt:
                # Draw an arrowhead
                angle = math.atan2(layout[tgt][1]-layout[src][1],
                    layout[tgt][0]-layout[src][0])
                a1 = (layout[tgt][0]-15*math.cos(angle-math.pi/10.),
                  layout[tgt][1]-15*math.sin(angle-math.pi/10.))
                a2 = (layout[tgt][0]-15*math.cos(angle+math.pi/10.),
                  layout[tgt][1]-15*math.sin(angle+math.pi/10.))
                context.move_to(*layout[tgt])
                context.line_to(*a1)
                context.line_to(*a2)
                context.line_to(*layout[tgt])
                context.fill()

        # Draw the vertices
        context.set_line_width(1)
        for idx, v in enumerate(self.vs):
            context.arc(layout[idx][0], layout[idx][1], vertex_sizes[idx]/2., 0, 2*math.pi)
            context.set_source_rgb(*vertex_colors[idx])
            context.fill_preserve()
            context.set_source_rgb(0., 0., 0.)
            context.stroke()
        del vertex_colors

        # Draw the vertex labels
        if not kwds.has_key("vertex_label") and "label" not in self.vs.attributes():
            vertex_labels = map(str, xrange(self.vcount()))
        elif kwds.has_key("vertex_label") and kwds["vertex_label"] is None:
            vertex_labels = [""] * self.vcount()
        else:
            vertex_labels = drawing.collect_attributes(self.vcount(), "vertex_label", "label", kwds, self.vs, config, None)
        vertex_dists = drawing.collect_attributes(self.vcount(), "vertex_dist", "dist", kwds, self.vs, config, 1, float)
        vertex_degrees = drawing.collect_attributes(self.vcount(), "vertex_degree", "degree", kwds, self.vs, config, -math.pi/4, float)
        context.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        context.set_font_size(14)

        for idx, v in enumerate(self.vs):
            xb, yb, w, h = context.text_extents(vertex_labels[idx])[:4]
            cx, cy = layout[idx]
            cx += math.cos(vertex_degrees[idx]) * vertex_dists[idx] * vertex_sizes[idx]
            cy += math.sin(vertex_degrees[idx]) * vertex_dists[idx] * vertex_sizes[idx]
            cx -= w/2. + xb
            cy -= h/2. + yb
            context.move_to(cx, cy)
            context.show_text(vertex_labels[idx])

        return

    def summary(self, verbosity=0):
        """Returns basic statistics about the graph in a string
        
        @param verbosity: the amount of statistics to be returned. 0 returns
          the usual statistics (node, edge count, directedness, number of
          strong components, density, reciprocity, average path length,
          diameter). 1 also returns the detailed degree distributions."""
        output=[]
        output.append("%d nodes, %d edges, %sdirected" % \
            (self.vcount(), self.ecount(), ["un", ""][self.is_directed()]))
        output.append("")
        output.append("Number of components: %d" % (len(self.clusters())+1))
        output.append("Diameter: %d" % self.diameter(unconn=True))
        output.append("Density: %.4f" % self.density())
        # output.append("Transitivity: %.4f" % self.transitivity())
        if self.is_directed():
            output.append("Reciprocity: %.4f" % self.reciprocity())
        output.append("Average path length: %.4f" % self.average_path_length())

        if verbosity>=1:
            maxdegree=self.maxdegree()
            binwidth=max(1, maxdegree/20)
            output.append("")
            output.append("Degree distribution:")
            output.append(str(self.degree_distribution(binwidth)))

            if self.is_directed():
                output.append("")
                output.append("Degree distribution (only in-degrees):")
                output.append(str(self.degree_distribution(binwidth, type=IN)))
                output.append("")
                output.append("Degree distribution (only out-degrees):")
                output.append(str(self.degree_distribution(binwidth, type=OUT)))

        return "\n".join(output)

    _format_mapping = {
          "ncol":       ("Read_Ncol", "write_ncol"),
          "lgl":        ("Read_Lgl", "write_lgl"),
          "graphmlz":   ("Read_GraphMLz", "write_graphmlz"),
          "graphml":    ("Read_GraphML", "write_graphml"),
          "gml":        ("Read_GML", "write_gml"),
          "net":        ("Read_Pajek", None),
          "pajek":      ("Read_Pajek", None),
          "dimacs":     ("Read_DIMACS", "write_dimacs"),
          "adjacency":  ("Read_Adjacency", "write_adjacency"),
          "adj":        ("Read_Adjacency", "write_adjacency"),
          "edgelist":   ("Read_Edgelist", "write_edgelist"),
          "edge":       ("Read_Edgelist", "write_edgelist"),
          "edges":      ("Read_Edgelist", "write_edgelist"),
          "pickle":     ("Read_Pickle", "write_pickle"),
          "svg":        (None, "write_svg")
    }

    _layout_mapping = {
        "circle": "layout_circle",
        "circular": "layout_circle",
        "fr": "layout_fruchterman_reingold",
        "fruchterman_reingold": "layout_fruchterman_reingold",
        "fr3d": "layout_fruchterman_reingold_3d",
        "fr_3d": "layout_fruchterman_reingold_3d",
        "fruchterman_reingold_3d": "layout_fruchterman_reingold_3d",
        "gfr": "layout_grid_fruchterman_reingold",
        "grid_fr": "layout_grid_fruchterman_reingold",
        "grid_fruchterman_reingold": "layout_grid_fruchterman_reingold",
        "kk": "layout_kamada_kawai",
        "kamada_kawai": "layout_kamada_kawai",
        "kk3d": "layout_kamada_kawai_3d",
        "kk_3d": "layout_kamada_kawai_3d",
        "kamada_kawai_3d": "layout_kamada_kawai_3d",
        "lgl": "layout_lgl",
        "large": "layout_lgl",
        "large_graph": "layout_lgl",
        "random": "layout_random",
        "random_3d": "layout_random_3d",
        "rt": "layout_reingold_tilford",
        "tree": "layout_reingold_tilford",
        "reingold_tilford": "layout_reingold_tilford",
        "rt_circular": "layout_reingold_tilford_circular",
        "reingold_tilford_circular": "layout_reingold_tilford_circular",
        "sphere": "layout_sphere",
        "spherical": "layout_sphere",
        "circle_3d": "layout_sphere",
        "circular_3d": "layout_sphere",
    }

    # After adjusting something here, don't forget to update the docstring
    # of Graph.layout if necessary!

def read(filename, *args, **kwds):
    """Loads a graph from the given filename.

    This is just a convenience function, calls L{Graph.Read} directly.
    All arguments are passed unchanged to L{Graph.Read}
    
    @param filename: the name of the file to be loaded
    """
    return Graph.Read(filename, *args, **kwds)
load=read

def write(filename, graph, *args, **kwds):
    """Saves a graph to the given file.

    This is just a convenience function, calls L{Graph.write} directly.
    All arguments are passed unchanged to L{Graph.write}

    @param filename: the name of the file to be written
    @param graph: the graph to be saved
    """
    return graph.write(filename, *args, **kwds)
save=write

config = configuration.init()

