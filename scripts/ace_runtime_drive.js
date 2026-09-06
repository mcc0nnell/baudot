#!/usr/bin/env node
'use strict';

const io = require('socket.io-client');

if (process.argv.length !== 6) {
  console.error('usage: ace_runtime_drive.js <port> <token> <username> <number>');
  process.exit(64);
}

const port = process.argv[2];
const token = process.argv[3];
const username = process.argv[4];
const number = process.argv[5];
const url = 'http://127.0.0.1:' + port;

let finished = false;
const timer = setTimeout(function () {
  if (!finished) {
    console.error('ACE Socket.IO drive timed out for ' + url);
    process.exit(2);
  }
}, 6000);

const socket = io.connect(url, {
  forceNew: true,
  reconnection: false,
  query: 'token=' + token
});

socket.on('connect', function () {
  socket.emit('outbound-call', {
    username: username,
    exten: number
  });

  setTimeout(function () {
    finished = true;
    clearTimeout(timer);
    socket.disconnect();
    console.log('ACE outbound-call emitted: ' + username + ' -> ' + number);
    process.exit(0);
  }, 900);
});

socket.on('connect_error', function (err) {
  finished = true;
  clearTimeout(timer);
  console.error('ACE Socket.IO connect_error: ' + (err && err.message ? err.message : err));
  process.exit(3);
});

socket.on('error', function (err) {
  console.error('ACE Socket.IO error: ' + (err && err.message ? err.message : err));
});
