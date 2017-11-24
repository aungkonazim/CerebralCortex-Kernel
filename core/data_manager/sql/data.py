# Copyright (c) 2017, MD2K Center of Excellence
# - Nasir Ali <nasir.ali08@gmail.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import mysql.connector

from core.data_manager.sql.kafka_offsets_handler import KafkaOffsetsHandler
from core.data_manager.sql.stream_handler import StreamHandler
from core.data_manager.sql.users_handler import UserHandler


class SqlData(StreamHandler, UserHandler, KafkaOffsetsHandler):
    def __init__(self, CC):
        self.CC = CC
        self.config = CC.config
        self.hostIP = self.config['mysql']['host']
        self.hostPort = self.config['mysql']['port']
        self.database = self.config['mysql']['database']
        self.dbUser = self.config['mysql']['db_user']
        self.dbPassword = self.config['mysql']['db_pass']
        self.datastreamTable = self.config['mysql']['datastream_table']
        self.kafkaOffsetsTable = self.config['mysql']['kafka_offsets_table']
        self.userTable = self.config['mysql']['user_table']

        self.dbConnection = mysql.connector.connect(host=self.hostIP, port=self.hostPort, user=self.dbUser,
                                                    password=self.dbPassword, database=self.database)
        self.cursor = self.dbConnection.cursor(dictionary=True)

    def __del__(self):
        if self.dbConnection:
            self.dbConnection.close()