import React, { useState, useEffect } from 'react';
import { Toast, Button } from 'react-bootstrap';
import { FiDownload, FiX, FiGift } from 'react-icons/fi';

const UpdateNotification = () => {
    const [updateInfo, setUpdateInfo] = useState(null);
    const [show, setShow] = useState(false);

    useEffect(() => {
        if (!window.api) return;
        const removeListener = window.api.onUpdateAvailable((info) => {
            console.log('Update available:', info);
            setUpdateInfo(info);
            setShow(true);
        });

        return () => {
            removeListener();
        };
    }, []);

    const handleDownload = () => {
        if (window.api && window.api.openReleasePage) {
            window.api.openReleasePage();
        }
        setShow(false);
    };

    const handleClose = () => {
        setShow(false);
    };

    if (!updateInfo) return null;

    return (
        <div
            style={{
                position: 'fixed',
                bottom: '20px',
                right: '20px',
                zIndex: 10000,
                minWidth: '300px'
            }}
        >
            <Toast show={show} onClose={handleClose} bg="dark" text="white">
                <Toast.Header closeButton={false} className="bg-primary text-white">
                    <FiGift className="me-2" />
                    <strong className="me-auto">New Update Available</strong>
                    <small>v{updateInfo.version}</small>
                    <button
                        type="button"
                        className="btn-close btn-close-white ms-2"
                        onClick={handleClose}
                        aria-label="Close"
                    />
                </Toast.Header>
                <Toast.Body className="bg-dark text-white">
                    <p className="mb-3">
                        A new version of RelSim is available!
                        <br />
                        <small className="text-muted">
                            Released: {new Date(updateInfo.releaseDate).toLocaleDateString()}
                        </small>
                    </p>
                    <div className="d-grid gap-2">
                        <Button variant="success" size="sm" onClick={handleDownload}>
                            <FiDownload className="me-2" />
                            Download v{updateInfo.version}
                        </Button>
                    </div>
                </Toast.Body>
            </Toast>
        </div>
    );
};

export default UpdateNotification;
