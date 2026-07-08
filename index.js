const cron = require('node-cron');
const { sync } = require('./scripts/sync.mjs');

cron.schedule('*/5 * * * *', () => {
    sync();
})