/* Preserve original research provenance while guarding authorized UI integration. */
'use strict';
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const frozen=require('./protected-files.json'),integration=require('./runtime-integration.json');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
function read(file,reader=fs.readFileSync){const change=integration.files[file];if(change){assert.equal(sha(reader(file)),change.authorized_runtime_sha256,'UNREVIEWED_RUNTIME_CHANGED: '+file);return reader(change.archive);}return reader(file);}
function verify(reader=fs.readFileSync){for(const [file,digest]of Object.entries(frozen))assert.equal(sha(read(file,reader)),digest,'BASELINE_CHANGED: '+file);}
function digests(){verify();return Object.fromEntries(Object.keys(frozen).map(file=>[file,sha(read(file))]));}
module.exports={read,verify,digests};
