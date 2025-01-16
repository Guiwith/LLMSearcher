from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, 
                           QTableWidget, QTableWidgetItem, QTimeEdit, QHeaderView)
from PyQt6.QtCore import QTime

class BatchTaskDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量任务设置")
        self.setMinimumSize(600, 400)
        self.tasks = []
        self.setupUI()
        
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # 创建表格
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["需求内容", "计划执行时间", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 100)
        layout.addWidget(self.table)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        add_button = QPushButton("添加任务")
        add_button.clicked.connect(self.add_task)
        button_layout.addWidget(add_button)
        
        delete_button = QPushButton("删除任务")
        delete_button.clicked.connect(self.delete_task)
        button_layout.addWidget(delete_button)
        
        confirm_button = QPushButton("确认")
        confirm_button.clicked.connect(self.accept)
        button_layout.addWidget(confirm_button)
        
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)

    def add_task(self):
        current_row = self.table.rowCount()
        self.table.insertRow(current_row)
        
        content_item = QTableWidgetItem("")
        self.table.setItem(current_row, 0, content_item)
        
        time_widget = QTimeEdit()
        time_widget.setDisplayFormat("HH:mm:ss")
        if current_row == 0:
            time_widget.setTime(QTime.currentTime())
        else:
            last_time = self.table.cellWidget(current_row-1, 1).time()
            next_time = last_time.addSecs(3600)
            time_widget.setTime(next_time)
        self.table.setCellWidget(current_row, 1, time_widget)
        
        status_item = QTableWidgetItem("等待中")
        self.table.setItem(current_row, 2, status_item)
        
    def delete_task(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
            
    def get_tasks(self):
        tasks = []
        for row in range(self.table.rowCount()):
            content = self.table.item(row, 0).text()
            time = self.table.cellWidget(row, 1).time()
            tasks.append({
                'content': content,
                'time': time,
                'status': self.table.item(row, 2).text()
            })
        return tasks 