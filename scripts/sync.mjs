import { google } from "googleapis"
import { promises, createWriteStream, existsSync} from "fs"
import { Writable, Readable } from "stream"
import { mkdir } from "fs/promises";
import sharp from "sharp"
import { Client } from "basic-ftp";

const credentials = JSON.parse(process.env.GOOGLE_APPLICATION_CREDENTIALS);

const hostingerFTPCredentials = {
        host: process.env.HOSTINGER_FTP_HOST,
        port: process.env.HOSTINGER_FTP_PORT,
        user: process.env.HOSTINGER_FTP_USERNAME,
        password: process.env.HOSTINGER_FTP_PASSWORD
    }

const auth = new google.auth.GoogleAuth({
    credentials,
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
async function saveMetaData(metadata) {

    let metaDataReadableStream = Readable.from(metadata);

    let hostinger_file_storage = new Client();

    try {
        await hostinger_file_storage.access(hostingerFTPCredentials);
        await hostinger_file_storage.uploadFrom(metaDataReadableStream, "domains/psychedelicqueenartistry.com/public_html/pictures.json");
        console.log("success");
    }
    catch(err) {
        console.log(err);
    }

    hostinger_file_storage.close();
}

async function getArtworkImagesOnDrive() {
    let response = await drive.files.list({
        q: `'${process.env.ARTWORK_IMAGES_FOLDER_ID}' in parents`
    });

    response = response.data.files;
    return response;
}

async function updateImages(metadata) {

    let pictureData = JSON.parse(metadata);
    let pictureDataIDs = new Set();

    pictureData.forEach((imgData) => {
        pictureDataIDs.add(imgData["ID"]);
    })

    
    let artworkImages = await getArtworkImagesOnDrive();

    artworkImages.forEach((driveImage) => {
        let temp = driveImage.name.split(".").slice(0, -1).join("");
        temp = temp.split(/(?=[A-Z])/);
        temp = temp.map((word) => {
            return word.toLowerCase();
        })

        driveImage.title = temp.join("-");
    })

    let hostingerFileStorage = new Client();
    let hostingerImages = [];

    try {
        await hostingerFileStorage.access(hostingerFTPCredentials);

        hostingerImages = (await hostingerFileStorage.list('domains/psychedelicqueenartistry.com/public_html/img/full')).map((picture) => {
            
            return picture.name.split(".")[0];
        });

        hostingerImages = new Set(hostingerImages);

    }
    catch(err) {
        console.log(err);
        process.exit(1);
    }
 
    for(const driveImage of artworkImages) {
        if(pictureDataIDs.has(driveImage.title))
        {
            if(hostingerImages.has(driveImage.title)) {
                hostingerImages.delete(driveImage.title);
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

                try {
                    let hostingerFileStorage = new Client();
                    await hostingerFileStorage.access(hostingerFTPCredentials);
                    
                    await hostingerFileStorage.uploadFrom(webpImage, `domains/psychedelicqueenartistry.com/public_html/img/full/${driveImage.title}.webp`);

                    let fourByThree = await webpImage.resize(metaData.width, Math.trunc(metaData.width * 3/4), {
                        fit: "cover"
                    })

                    await hostingerFileStorage.uploadFrom(fourByThree, `domains/psychedelicqueenartistry.com/public_html/img/4x3/${driveImage.title}.webp`);

                    console.log(`uploaded ${driveImage.title}`)
                }
                catch(err) {
                    console.log(err);
                    process.exit(1);
                }
            }


            //await webpImage.toFile(`public/img/full/${driveImage.title}.webp`);
            
            /*
            await webpImage.resize(metaData.width, Math.trunc(metaData.width * 3/4), {
                fit: "cover"
            }).toFile(`public/img/4x3/${driveImage.title}.webp`);

            */
        }
    }
    console.log("Uploading complete!");

    //names remaining in localImages list should be removed

    for(const hostingerImage of hostingerImages) {
        try {
            let hostingerFileStorage = new Client();

            await hostingerFileStorage.access(hostingerFTPCredentials);

            await hostingerFileStorage.remove(`domains/psychedelicqueenartistry.com/public_html/img/full/${hostingerImage}.webp`);

            await hostingerFileStorage.remove(`domains/psychedelicqueenartistry.com/public_html/img/4x3/${hostingerImage}.webp`);
        }
        catch(err) {
            console.log(err);
            process.exit(1);
        }
    }
}

export async function sync() {
    let metaData = await getMetaData();
    await saveMetaData(metaData);
    await updateImages(metaData);
    console.log("SYNC COMPLETE");
}
