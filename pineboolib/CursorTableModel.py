# # -*- coding: utf-8 -*-
import math, random
from pineboolib.flcontrols import ProjectClass
from pineboolib import decorators
from pineboolib.qsaglobals import ustr
import pineboolib

from pineboolib.utils import filedir

from PyQt5 import QtCore, QtGui
from pineboolib.fllegacy.FLSqlQuery import FLSqlQuery
from pineboolib.fllegacy.FLFieldMetaData import FLFieldMetaData
from pineboolib.fllegacy.FLTableMetaData import FLTableMetaData
import traceback

import threading

import time, itertools

DEBUG = False

DisplayRole = QtCore.Qt.DisplayRole 
EditRole = QtCore.Qt.EditRole
Horizontal = QtCore.Qt.Horizontal
Vertical = QtCore.Qt.Vertical
QVariant_invalid = None
QVariant = str()
QAbstractTableModel_headerData = QtCore.QAbstractTableModel.headerData
class CursorTableModel(QtCore.QAbstractTableModel):
    rows = 15
    cols = 5
    _cursor = None
    _cursorConn = None
    USE_THREADS = False
    USE_TIMER = False
    CURSOR_COUNT = itertools.count()
    rowsLoaded = 0
    where_filters = {}
    _table = None
    
    def __init__(self, action, project, conn, *args):
        super(CursorTableModel,self).__init__(*args)
        from pineboolib.qsaglobals import aqtt
        

        self.rowsLoaded = 0
        self.where_filters = {}
        self._cursorConn = conn
        
        self._action = action
        self._prj = project
        
        self.USE_THREADS = self._prj.conn.driver().useThreads()
        self.USE_TIMER = self._prj.conn.driver().useTimer()
        
        if action and action.table:
            try:
                self._table = project.tables[action.table]
            except:
                #print("CursortableModel : Tabla %s no declarada en project.tables" % action.table)
                self._table = None
                return None
            
            self._metadata = project.conn.manager().metadata(self._table.name)
        else:
            raise AssertionError
        
        self.sql_fields = []
        self.field_aliases = []
        self.field_type = []
        self.field_metaData = []

        # Indices de busqueda segun PK y CK. Los array "pos" guardan las posiciones
        # de las columnas afectadas. PK normalmente valdrá [0,].
        # CK puede ser [] o [2,3,4] por ejemplo.
        # En los IDX tendremos como clave el valor compuesto, en array, de la clave.
        # Como valor del IDX tenemos la posicion de la fila.
        # Si se hace alguna operación en _data como borrar filas intermedias hay
        # que invalidar los indices. Opcionalmente, regenerarlos.
        self.pkpos = []
        self.ckpos = []
        self.pkidx = {}
        self.ckidx = {}
        self.indexes_valid = False # Establecer a False otra vez si el contenido de los indices es erróneo.
        #for field in self._table.fields:
            #if field.visible_grid:
            #self.sql_fields.append(field.name())
            #self.field_metaData.append(field)
        #    self.tableMetadata().addField(field)
        self._data = []
        self._vdata = []
        self._column_hints = []
        self.cols = len(self.tableMetadata().fieldList())
        self.col_aliases = [ str(self.tableMetadata().indexFieldObject(i).alias()) for i in range(self.cols) ]
        self.fetchLock = threading.Lock()
        self.rows = 0
        self.rowsLoaded = 0
        self.where_filters = {}
        self.where_filters["main-filter"] = None
        self.where_filters["filter"] = None
        self.pendingRows = 0
        self.lastFetch = 0
        self.fetchedRows = 0
        self._showPixmap = True
        
        if self.USE_THREADS == True:
            self.threadFetcher = threading.Thread(target=self.threadFetch)
            self.threadFetcherStop = threading.Event()
        
        if self.USE_TIMER == True:
            self.timer = QtCore.QTimer()
            self.timer.timeout.connect(self.updateRows)
            self.timer.start(1000)
            
        self.canFetchMore = True         
        self.refresh()


    def metadata(self):
        #print("CursorTableModel: METADATA: " + self._table.name)
        return self._metadata

    def canFetchMore(self,index):
        return self.canFetchMore
        ret = self.rows > self.rowsLoaded
        #print("canFetchMore: %r" % ret)
        return ret
    
    def data(self, index, role):
        #print("Data ", index, role)
        #print("Registros", self.rowCount())
        #roles
        #0 QtCore.Qt.DisplayRole
        #1 QtCore.Qt.DecorationRole
        #2 QtCore.Qt.EditRole
        #3 QtCore.Qt.ToolTipRole
        #4 QtCore.Qt.StatusTipRole
        #5 QtCore.Qt.WhatThisRole
        #6 QtCore.Qt.FontRole
        #7 QtCore.Qt.TextAlignmentRole
        #8 QtCore.Qt.BackgroundRole
        #9 QtCore.Qt.ForegroundRole
        
        
        
        
        
        row = index.row()
        col = index.column()
        field = self.metadata().indexFieldObject(col)
        _type = field.type()
        r = None
        
        if r is None:
            r = [ str(x) for x in self._data[row] ]
            self._data[row] = r
        d = r[col]
        
        if role == QtCore.Qt.TextAlignmentRole:
            if _type in ("int","double","uint"):
                d = QtCore.Qt.AlignRight
            elif _type in ("bool","unlock","date","time","pixmap"):
                d = QtCore.Qt.AlignCenter
            else:
                d = None
            
            return d
        
        
        if role == DisplayRole or role == EditRole:
            #r = self._vdata[row]
            if _type == "bool":
                if d in ("True", "1"):
                    d = "Sí"
                else:
                    d = "No"
            
            if _type in ("unlock","pixmap"):
                #FIXME: Aquí cargaremos imagen en el futuro
                d = None
            
            return d
        
        if role == QtCore.Qt.DecorationRole:
            icon = None
            if _type == "unlock":
                
                if d in ("True","1"):
                    icon = QtGui.QIcon(filedir("icons","unlock.png"))
                else:
                    icon = QtGui.QIcon(filedir("icons","lock.png"))
            
            if _type == "pixmap" and self._showPixmap:
                pass
                
                
            
            return icon
                    
        
        if role == QtCore.Qt.BackgroundRole:
            if _type == "bool":
                if d in ("True", "1"):
                    d = QtGui.QBrush(QtCore.Qt.green)
                else:
                    d = QtGui.QBrush(QtCore.Qt.red)
            else:
                d = None
            
            return d
        
        if role == QtCore.Qt.ForegroundRole:
            if _type == "bool" and not d in ("True","1"):
                d = QtGui.QBrush(QtCore.Qt.white)
            else:
                d = None
            
            return d
            
            #if row > self.rowsLoaded *0.95 - 200 and time.time() - self.lastFetch> 0.3: self.fetchMore(QtCore.QModelIndex())
            #d = self._vdata[row*1000+col]
            #if type(d) is str:
            #    d = QVariant(d)
            #    self._vdata[row*1000+col] = d
        return None 
            

        return QVariant_invalid
    
    def setShowPixmap(self, show):
        self._showPixmap = show
    
    def threadFetch(self):
        #ct = threading.current_thread()
        #print("Thread: FETCH (INIT)")
        tiempo_inicial = time.time()
        #sql = """FETCH %d FROM %s""" % (2000,self._curname)
        #conn = self._cursorConn.db()
        self.refreshFetch(2000,self._curname, self.tableMetadata().name(), self._cursor)
        #try: 
        #    self._cursor.execute(sql)
        #except Exception:
            #conn.rollback()
        #    print("CursorTableModel.threadFetch :: ERROR:" , traceback.format_exc())
            
        tiempo_final = time.time()
        if DEBUG: 
            if tiempo_final - tiempo_inicial > 0.2:
                print("Thread: ", sql, "time: %.3fs" % (tiempo_final - tiempo_inicial))
        
        
        
    def updateRows(self):
        if self.USE_THREADS == True:
            ROW_BATCH_COUNT = 200 if self.threadFetcher.is_alive() else 0
        elif self.USE_TIMER == True:
            ROW_BATCH_COUNT = 200 if self.timer.isActive() else 0
        else:
            return
        
        parent = QtCore.QModelIndex()
        fromrow = self.rowsLoaded
        torow = self.fetchedRows - ROW_BATCH_COUNT - 1
        if torow - fromrow < 10: return
        if DEBUG: print("Updaterows %s (UPDATE:%d)" % (self._table.name, torow - fromrow +1) )
    
        self.beginInsertRows(parent, fromrow, torow)
        self.rowsLoaded = torow + 1
        self.endInsertRows()
        #print("fin refresco modelo tabla %r , query %r, rows: %d %r" % (self._table.name, self._table.query_table, self.rows, (fromrow,torow)))
        topLeft = self.index(fromrow,0)
        bottomRight = self.index(torow,self.cols-1)
        self.dataChanged.emit(topLeft,bottomRight)
        
        
    def fetchMore(self,index, tablename = None, where_filter = None):
        tiempo_inicial = time.time()
        #ROW_BATCH_COUNT = min(200 + self.rowsLoaded // 10, 1000)
        ROW_BATCH_COUNT = 1000
        
        parent = index
        fromrow = self.rowsLoaded
        torow = self.rowsLoaded + ROW_BATCH_COUNT # FIXME: Hay que borrar luego las que no se cargaron al final...
        if self.fetchedRows - ROW_BATCH_COUNT - 1  > torow:
            torow = self.fetchedRows - ROW_BATCH_COUNT - 1
            
        #print("refrescando modelo tabla %r , query %r, rows: %d %r" % (self._table.name, self._table.query_table, self.rows, (fromrow,torow)))
        if torow < fromrow: return
        
        #print("QUERY:", sql)

        if self.fetchedRows <= torow and self.canFetchMore: 
            
            if self.USE_THREADS == True and self.threadFetcher.is_alive(): self.threadFetcher.join()
            
            if tablename == None:
                tablename = self.tableMetadata().name()
            
            if where_filter == None:
                where_filter = self.where_filter
            
            c_all = self._prj.conn.driver().fetchAll(self._cursor, tablename, where_filter, ", ".join(self.sql_fields), self._curname)
            newrows = len(c_all) #self._cursor.rowcount
            from_rows = self.rows
            self._data += c_all
            self._vdata += [None] * newrows
            self.fetchedRows+=newrows
            self.rows += newrows
            self.canFetchMore = newrows > 0

            self.pendingRows = 0
            self.indexUpdateRowRange((from_rows,self.rows))
            if self.USE_THREADS == True:
                self.threadFetcher = threading.Thread(target=self.threadFetch)
                self.threadFetcher.start()

        if torow > self.rows -1: torow = self.rows -1
        if torow < fromrow: return
        self.beginInsertRows(parent, fromrow, torow)

        if fromrow == 0:
            data_trunc = self._data[:200]
            for row in data_trunc:
                for r, val in enumerate(row):
                    txt = str(val)
                    ltxt = len(txt)
                    newlen = int(40 + math.tanh(ltxt/3000.0) * 35000.0)
                    self._column_hints[r] +=  newlen
            for r in range(len(self._column_hints)):
                self._column_hints[r] /=  len(self._data[:200]) + 1
            self._column_hints = [ int(x) for x in self._column_hints ]
            
        self.indexes_valid = True
        self.rowsLoaded = torow + 1
        self.endInsertRows()
        #print("fin refresco modelo tabla %r , query %r, rows: %d %r" % (self._table.name, self._table.query_table, self.rows, (fromrow,torow)))
        topLeft = self.index(fromrow,0)
        bottomRight = self.index(torow,self.cols-1)
        self.dataChanged.emit(topLeft,bottomRight)
        tiempo_final = time.time()
        self.lastFetch = tiempo_final
        #if self.USE_THREADS == True and not self.threadFetcher.is_alive() and self.pendingRows > 0: 
        #    self.threadFetcher = threading.Thread(target=self.threadFetch)
        #    self.threadFetcherStop = threading.Event()
        #    self.threadFetcher.start()
        
        if tiempo_final - tiempo_inicial > 0.2:
            print("fin refresco tabla '%s'  :: rows: %d %r  ::  (%.3fs)" % ( self._table.name, self.rows, (fromrow,torow), tiempo_final - tiempo_inicial))
 

    def refresh(self):
        if not self._table:
            print("ERROR: CursorTableModel :: No hay tabla")
            return 
            
        parent = QtCore.QModelIndex()
        oldrows = self.rowsLoaded
        self.beginRemoveRows(parent, 0, oldrows )
        if self.USE_THREADS == True:
            self.threadFetcherStop.set()
            if self.threadFetcher.is_alive(): self.threadFetcher.join()
            
        self.rows = 0
        self.rowsLoaded = 0
        self.fetchedRows = 0
        self.sql_fields = []
        self.pkpos = []
        self.ckpos = []
        self._data = []
        self.endRemoveRows()
        if oldrows > 0:
            self.rowsRemoved.emit(parent, 0, oldrows - 1)
        where_filter = None
        
        for k, wfilter in sorted(self.where_filters.items()):
            if wfilter is None: continue
            wfilter = wfilter.strip()
            if not wfilter: continue
            if not where_filter:
                where_filter = wfilter
            elif not wfilter in where_filter:
                where_filter += " AND " + wfilter
        if not where_filter:
            where_filter = "1 = 1"
        
        self.where_filter = where_filter
        
        #for f in self.where_filters.keys():
        #    print("Filtro %s --> %s" % (f, self.where_filters[f]))
        
        #print("Filtro final", self.where_filter)
        
        
        
        #print("Filtro", where_filter)
        
        self._cursor = self._cursorConn.cursor()
        # FIXME: Cuando la tabla es una query, aquí hay que hacer una subconsulta.
        # TODO: Convertir esto a un cursor de servidor (hasta 20.000 registros funciona bastante bien)
        if self._table.query_table:
            # FIXME: Como no tenemos soporte para Queries, desactivamos el refresh.
            print("No hay soporte para CursorTableModel con Queries: name %r , query %r" % (self._table.name, self._table.query_table))
            
            return
        
        if not self.tableMetadata():
            return
        
        for n,field in enumerate(self.tableMetadata().fieldList()):
            #if field.visibleGrid():
            #    sql_fields.append(field.name())
            if field.isPrimaryKey(): self.pkpos.append(n)
            if field.isCompoundKey(): self.ckpos.append(n)

            self.sql_fields.append(field.name())
        self._curname = "cur_" + self._table.name + "_%08d" % (next(self.CURSOR_COUNT))
        
        self._prj.conn.driver().refreshQuery(self._curname, ", ".join(self.sql_fields),self.tableMetadata().name(), where_filter, self._cursor, self._cursorConn.db())
        
            
        self.refreshFetch(1000,self._curname, self.tableMetadata().name(), self._cursor)

        self.rows = 0
        self.canFetchMore = True
        #print("rows:", self.rows)
        self.pendingRows = 0

        self._column_hints = [120.0] * len(self.sql_fields)
        #self.threadFetcher = threading.Thread(target=self.threadFetch)
        #self.threadFetcherStop = threading.Event()
        #self.threadFetcher.start()
        self.fetchMore(parent, self.tableMetadata().name(),where_filter)
    
    def refreshFetch(self, number, curname, tablename, cursor):
        self._prj.conn.driver().refreshFetch(number, curname, tablename, cursor, ", ".join(self.sql_fields), self.where_filter)
        
    

    def indexUpdateRow(self, rownum):
        row = self._data[rownum]
        if self.pkpos:
            key = tuple([ row[x] for x in self.pkpos ])
            self.pkidx[key] = rownum
        if self.ckpos:
            key = tuple([ row[x] for x in self.ckpos ])
            self.ckidx[key] = rownum

    def indexUpdateRowRange(self, rowrange):
        rows = self._data[rowrange[0]:rowrange[1]]
        if self.pkpos:
            for n,row in enumerate(rows):
                key = tuple([ row[x] for x in self.pkpos ])
                self.pkidx[key] = n + rowrange[0]
        if self.ckpos:
            for n,row in enumerate(rows):
                key = tuple([ row[x] for x in self.ckpos ])
                self.ckidx[key] = n + rowrange[0]

    def value(self, row, fieldName):
        if row == None : return None
        if row < 0 or row >= self.rows: return None
        col = self.metadata().indexPos(fieldName)
        campo = self._data[row][col]

        type_ = self.metadata().field(fieldName).type()
        
        if type_ in ("serial", "uint", "int"):
            if not campo == None and not campo == "None":
                campo = int(campo)
        """
        if self.metadata().field(fieldname).type() == "pixmap":
            q = FLSqlQuery()
            q.setSelect("contenido")
            q.setFrom("fllarge")
            q.setWhere("refkey == '%s'" % campo)
            q.exec_()
            q.first()
            return q.value(0)
        else:
            return campo
        """
        return campo

        """
        value = None
        if row < 0 or row >= self.rows: return value
        try:
            #col = self.sql_fields.index(fieldname)
            col = self._prj.conn.manager.metadata(self._table.name).fieldIndex(fieldname)
        except:
            return value
        if self.field_type[col] == 'pixmap':
            campo = self._data[row][col]
            cur = pineboolib.project.conn.cursor()
            sql = "SELECT contenido FROM fllarge WHERE refkey ='%s'" % campo
            cur.execute(sql)
            for ret, in cur:
                value = ret
        else:
            value = self._data[row][col]
        return value
        """
    def updateValuesDB(self, pKValue, dict_update):
        row = self.findPKRow([pKValue])
        if row is None:
            raise AssertionError("Los indices del CursorTableModel no devolvieron un registro (%r)" % (pKValue))

        if self.value(row, self.pK()) != pKValue:
            raise AssertionError("Los indices del CursorTableModel devolvieron un registro erroneo: %r != %r" % (self.value(row, self.pK()), pKValue))

        self.setValuesDict(row, dict_update)
        pkey_name = self.tableMetadata().primaryKey()
        # TODO: la conversion de mogrify de bytes a STR va a dar problemas con los acentos...
        typePK_ = self.tableMetadata().field(self.tableMetadata().primaryKey()).type()
        pKValue = self._prj.conn.manager().formatValue(typePK_, pKValue, False)
        #if typePK_ == "string" or typePK_ == "pixmap" or typePK_ == "stringlist" or typePK_ == "time" or typePK_ == "date":
            #pKValue = str("'" + pKValue + "'")
            
        where_filter = "%s = %s" % (pkey_name, pKValue)
        update_set = []

        for key, value in dict_update.items():
            type_ = self.tableMetadata().field(key).type()
            #if type_ == "string" or type_ == "pixmap" or type_ == "stringlist" or type_ == "time" or type_ == "date":
                #value = str("'" + value + "'")
            value = self._prj.conn.manager().formatValue(type_, value, False)
            #update_set.append("%s = %s" % (key, (self._cursor.mogrify("%s",[value]))))
            update_set.append("%s = %s" % (key, value))

        update_set_txt = ", ".join(update_set)
        sql = """UPDATE %s SET %s WHERE %s RETURNING *""" % (self.tableMetadata().name(), update_set_txt, where_filter)
        print("MODIFYING SQL :: ", sql)
        self._cursor.execute(sql)
        returning_fields = [ x[0] for x in self._cursor.description ]

        for orow in self._cursor:
            dict_update = dict(zip(returning_fields, orow))
            self.setValuesDict(row, dict_update)



    """
    Asigna un valor una fila usando un diccionario
    @param row. Columna afectada
    @param update_dict. array clave-valor indicando el listado de claves y valores a actualizar
    """
    @decorators.BetaImplementation
    def setValuesDict(self, row, update_dict):

        if DEBUG: print("CursorTableModel.setValuesDict(row %s) = %r" % (row, update_dict))

        try:
            if isinstance(self._data[row], tuple):
                self._data[row] = list(self._data[row])
            r = self._vdata[row]
            if r is None:
                r = [ str(x) for x in self._data[row] ]
                self._vdata[row] = r
            colsnotfound = []
            for fieldname,value in update_dict.items():
                #col = self.metadata().indexPos(fieldname)
                try:
                    col = self.sql_fields.index(fieldname)
                    self._data[row][col] = value
                    r[col] = value
                except ValueError:
                    colsnotfound.append(fieldname)
            if colsnotfound:
                print("CursorTableModel.setValuesDict:: columns not found: %r" % (colsnotfound))
            self.indexUpdateRow(row)

        except Exception:

            print("CursorTableModel.setValuesDict(row %s) = %r :: ERROR:" % (row, update_dict), traceback.format_exc())


    """
    Asigna un valor una celda
    @param row. Columna afectada
    @param fieldname. Nonbre de la fila afectada. Se puede obtener la columna con self.metadata().indexPos(fieldname)
    @param value. Valor a asignar. Puede ser texto, pixmap, etc...
    """
    def setValue(self, row, fieldname, value):
        # Reimplementación para que todo pase por el método genérico.
        self.setValuesDict(self, row, { fieldname : value } )
    
    """
    Crea una nueva linea en el tableModel
    @param buffer . PNBuffer a añadir
    """
    def Insert(self, cursor):
        #Metemos lineas en la tabla de la bd
        buffer = cursor.buffer()
        campos = None
        valores = None
        for b in buffer.fieldsList():
            value = None
            if buffer.value(b.name) == None:
                value = buffer.cursor_.d.db_.manager().metadata(buffer.cursor_.d.curName_).field(b.name).defaultValue()
            else:
                value = buffer.value(b.name)
            if not value == None: # si el campo se rellena o hay valor default
                value = self._prj.conn.manager().formatValue(b.type_, value, False)
                if not campos:
                    campos = b.name
                    valores = value
                else:
                    campos = u"%s,%s" % (campos, b.name)
                    valores = u"%s,%s" % ( valores, value)
        if campos:
            sql = "INSERT INTO %s (%s) VALUES (%s)" % (buffer.cursor_.d.curName_, campos, valores)
            #conn = self._cursorConn.db()
            try:
                print(sql)
                self._cursor.execute(sql)
                self.refresh()
            except Exception:
                print("CursorTableModel.Insert() :: ERROR:" , traceback.format_exc())
                #conn.rollback()
                return False
                  
            #conn.commit()    
            
            return True
        
    def Delete(self, cursor):
        pKName = self.tableMetadata().primaryKey()
        typePK = self.tableMetadata().field(pKName).type()
        tableName = self.tableMetadata().name()
        sql = "DELETE FROM %s WHERE %s = %s" % (tableName , pKName , self._prj.conn.manager().formatValue(typePK , self.value(cursor.d._currentregister, pKName), False))
        #conn = self._cursorConn.db()
        try:
            self._cursor.execute(sql)         
        except Exception:
            print("CursorTableModel.Delete() :: ERROR:" , traceback.format_exc())
            conn.rollback()
            return
        
        #conn.commit()   
        self.refresh()
        

    def findPKRow(self, pklist):
        if not isinstance(pklist, (tuple, list)):
            raise ValueError("findPKRow expects a list as first argument. Enclose PK inside brackets [self.pkvalue]")
        if not self.indexes_valid:
            for n in range(self.rows):
                self.indexUpdateRow(n)
            self.indexes_valid = True
        pklist = tuple(pklist)
        if pklist not in self.pkidx:
            print("CursorTableModel.findPKRow:: PK not found: %r (requires list, not integer or string)" % pklist)
            return None
        return self.pkidx[pklist]

    def findCKRow(self, cklist):
        if not isinstance(cklist, (tuple, list)):
            raise ValueError("findCKRow expects a list as first argument.")
        if not self.indexes_valid:
            for n in range(self.rows):
                self.indexUpdateRow(n)
            self.indexes_valid = True
        cklist = tuple(cklist)
        if cklist not in self.ckidx:
            print("CursorTableModel.findCKRow:: CK not found: %r (requires list, not integer or string)" % cklist)
            return None
        return self.ckidx[cklist]


    def pK(self): #devuelve el nombre del campo pk
        return self.tableMetadata().primaryKey()
        #return self._pk

    def fieldType(self, fieldName): # devuelve el tipo de campo
        field = self.tableMetadata().field(fieldName)
        if field:
            return field.type()
        else:
            return None
        """
        value = None
        try:
            if not fieldName is None:
                value = self.field_metaData[self.sql_fields.index(fieldName)].type()
            else:
                value = None
            return value
        except:
            print("CursorTableModel: No se encuentra el campo %s" % fieldName)
            return None

        """
    def alias(self, fieldName):
        return self.tableMetadata().field(fieldName).alias()
        """
        value = None
        try:
            value = self.field_metaData[self.sql_fields.index(fieldName)].alias()
            return value
        except:
            return value
        """
    def columnCount(self, parent = None):
        return self.cols
        if parent is None: parent = QtCore.QModelIndex()
        if parent.isValid(): return 0
        #print(self.cols)
        print("colcount", self.cols)
        return self.cols

    def rowCount(self, parent = None):
        return self.rowsLoaded
        if parent is None: parent = QtCore.QModelIndex()
        if parent.isValid(): return 0
        print("rowcount", self.rows)
        return self.rows

    def headerData(self, section, orientation, role):
        if role == DisplayRole:
            if orientation == Horizontal:
                return self.col_aliases[section]
            elif orientation == Vertical:
                return section +1
        return QVariant_invalid
            
        return QAbstractTableModel_headerData(self, section, orientation, role)

    def fieldMetadata(self, fieldName):
        return self.tableMetadata().field(fieldName)
        """
        try:
            pos = self.field_metaData(fieldName)
            return self.field_metaData[pos]
        except:
            return False
            #print("CursorTableModel: %s.%s no hay datos" % ( self._table.name, fieldName ))
        """
    def tableMetadata(self):
        return self._prj.conn.manager().metadata(self._table.name)




