import { google } from "googleapis"
import { promises, createWriteStream, existsSync} from "fs"
import { Writable } from "stream"
import { mkdir } from "fs/promises";
import sharp from "sharp"

const auth = new google.auth.GoogleAuth({
    keyFile: process.env.KEYFILE,
    scopes: [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
});

const sheets = google.sheets({
    version: 'v4',
    auth
});

const drive = google.drive({
    version: 'v3',
    auth
});

// fetch meta-data from google drive
async function getMetaData() {

    let response = await sheets.spreadsheets.values.get({
        spreadsheetId: process.env.SPREADSHEET_ID,
        range:"Sheet1"
    });

    response = response.data.values;

    let columnNames = response[0];
    let temp = [];

    response.slice(1).forEach((row, rowIndex) => {
        temp[rowIndex] = {};
        columnNames.forEach((column, columnIndex) => {
            temp[rowIndex][column] = row[columnIndex];
        })
    });

    let jsonObject = JSON.stringify(temp);
    return jsonObject;
}

// saves metadata into json file
async function saveMetaData(metadata, filename) {
    await promises.writeFile(filename, metadata, 'utf8');
}

async function getArtworkImagesOnDrive() {
    let response = await drive.files.list({
        q: `'${process.env.ARTWORK_IMAGES_FOLDER_ID}' in parents`
    });

    response = response.data.files;
    return response;
}

async function updateImages() {

    if(!existsSync('public/img/full')) {
        await mkdir('public/img/full');
    }

    if(!existsSync('public/img/4x3')) {
        await mkdir('public/img/4x3');
    }
    
    let artworkImages = await getArtworkImagesOnDrive();

    artworkImages.forEach((driveImage) => {
        let temp = driveImage.name.split(".")[0];
        temp = temp.split(/(?=[A-Z])/);
        temp = temp.map((word) => {
            return word.toLowerCase();
        })

        driveImage.title = temp.join("-");
    })

    let localImages = (await promises.readdir('public/img/full')).map((image) => {
        return image.split(".")[0];
    });

    localImages = new Set(localImages);

    for(const driveImage of artworkImages) {
        if(localImages.has(driveImage.title)) {
            localImages.delete(driveImage.title);
        }
        else if(driveImage.name.split(".")[1] !== "HEIC"){
            // driveImage not in local storage, download into public/img/website_images folder
            let imageBlob = await drive.files.get({
                fileId: driveImage.id,
                alt: 'media'
            });

            let imageBuffer = await imageBlob.data.arrayBuffer();
            let webpImage = await sharp(imageBuffer).webp()

            let metaData = await webpImage.metadata();

            await webpImage.toFile(`public/img/full/${driveImage.title}.webp`);
            
            await webpImage.resize(metaData.width, Math.trunc(metaData.width * 3/4), {
                fit: "cover"
            }).toFile(`public/img/4x3/${driveImage.title}.webp`);
        }
    }

    //names remaining in localImages list should be removed
    for(const localImage of localImages) {
        //delete full version
        await promises.unlink(`public/img/full/${localImage}.webp`);

        //delete 4x3 version
        await promises.unlink(`public/img/4x3/${localImage}.webp`);
    }
}

let metaData = await getMetaData();
await saveMetaData(metaData, "src/data/pictures.json");
await updateImages();
